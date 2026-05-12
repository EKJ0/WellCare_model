"""Load real WellCare check-in data into the shape scenarios.generate() emits.

Input:  checkins.csv (export from checkin-app.html or checkin.py)
Output: pandas.DataFrame with the columns the daily pipeline expects,
        ready to feed into add_rolling_features() and train.py.

Handles common CSV-export quirks:
  - person_id / team_id mapping (one person *is* a "team" of one)
  - date / week_start / submitted_at strings (any common format) ->
    integer day index per person, starting at 0
  - missing optional columns (events, on_call_load) -> sensible defaults
  - Maslach mini -> burnout label, if present
  - duplicate (person, date) rows -> last submission wins"""

from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

from scenarios import RAW_COLS

OUT = Path(__file__).resolve().parent
DEFAULT_PATH = OUT / "checkins.csv"


def from_csv(path: str | Path = DEFAULT_PATH) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"No check-in file at {path}. "
            f"Export one from checkin-app.html (Profile -> Export CSV) "
            f"or run `python checkin.py`."
        )

    df = pd.read_csv(path)

    # --- Column normalization ---------------------------------------------
    rename = {
        "Email Address":  "person_id",
        "Email":          "person_id",
        "Timestamp":      "submitted_at",
        "when":           "date",
        "Date":           "date",
        "Day":            "date",
        "Week of":        "date",
        "week_start":     "date",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    if "person_id" not in df.columns:
        raise ValueError(f"`person_id` column missing in {path.name}")
    if "team_id" not in df.columns:
        df["team_id"] = df["person_id"]
    if "events" not in df.columns:
        df["events"] = ""
    df["events"] = df["events"].fillna("").astype(str)

    # --- Maslach mini -> burnout label ------------------------------------
    mbi_cols = ["mbi_drained", "mbi_fulfilled", "mbi_cynical"]
    if all(c in df.columns for c in mbi_cols) and "burnout" not in df.columns:
        score = (df["mbi_drained"] + (8 - df["mbi_fulfilled"]) + df["mbi_cynical"]) / 3
        df["burnout"] = (score >= 4.5).astype(int)

    if "burnout" not in df.columns:
        df["burnout"] = np.nan

    # --- Day index per person ---------------------------------------------
    if "date" not in df.columns and "submitted_at" in df.columns:
        df["date"] = df["submitted_at"]
    if "date" not in df.columns:
        raise ValueError(
            "CSV needs a `date` (or `when` / `submitted_at`) column "
            "to anchor each daily check-in.")
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True).dt.tz_localize(None)
    if df["date"].isna().any():
        bad = int(df["date"].isna().sum())
        raise ValueError(f"{bad} rows have unparseable `date` values")

    # Floor to the calendar day so multiple submits the same day merge.
    df["date_day"] = df["date"].dt.floor("D")
    df = df.sort_values(["person_id", "date_day", "date"])
    # Last submission of the day wins.
    df = df.drop_duplicates(subset=["person_id", "date_day"], keep="last")
    df["day"] = (df.groupby("person_id")["date_day"]
                   .rank(method="dense").astype(int) - 1)
    df["week"] = df["day"] // 7   # convenience for old grouping code

    # --- Required raw columns + types -------------------------------------
    missing = [c for c in RAW_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"missing required signal columns: {missing}. "
            f"See survey_template.md / checkin-app.html for the expected schema."
        )
    for c in RAW_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # --- Final column ordering -------------------------------------------
    keep = (["person_id", "team_id", "day", "week", "date"]
            + list(RAW_COLS) + ["events", "burnout"])
    return df[keep].reset_index(drop=True)


def summary(df: pd.DataFrame) -> dict:
    """Quick stats for sanity-checking. Prints + returns."""
    n_people = int(df["person_id"].nunique())
    days_per_person = df.groupby("person_id")["day"].nunique()
    labeled = int(df["burnout"].notna().sum())
    s = {
        "rows":                   int(len(df)),
        "unique_people":          n_people,
        "median_days_per_person": float(days_per_person.median()),
        "min_days_per_person":    int(days_per_person.min()),
        "max_days_per_person":    int(days_per_person.max()),
        "labeled_rows":           labeled,
        "positive_rate":          (float(df["burnout"].mean())
                                   if labeled else None),
    }
    print("Real daily-data summary:")
    for k, v in s.items():
        print(f"  {k:<24} {v}")
    return s


if __name__ == "__main__":
    df = from_csv()
    summary(df)
