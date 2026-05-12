"""Daily check-in scenario generator for WellCare burnout-risk modeling.

Each person has stable baselines for hours, sleep, mood, stress, manager
support, peer support, deadline pressure, and on-call load. Events
(deadline crunch, reorg, layoff, on-call rotation, PTO, recognition,
personal shock) perturb those signals across one or more *days*.

A latent 'burnout reservoir' R_t accumulates pressure minus recovery
day-by-day. The binary label is sampled from a logistic of R_t. The
reservoir is observable in the dataframe (prefixed with `_`) but is
NOT used as a model feature — that's the point: the model has to
infer risk from the noisy daily signals alone.

Column conventions match the check-in app exactly:
  - one row = one person-day check-in
  - hours       : hours WORKED THAT DAY            (0–16)
  - sleep       : hours SLEPT THE NIGHT BEFORE     (3–11)
  - mood        : self-reported now                (1–10)
  - stress      : self-reported now                (1–10)
  - mgr_support : felt support FROM MANAGER TODAY  (1–10)
  - peer_support: felt support FROM PEERS TODAY    (1–10)
  - deadline_pressure: workload pressure TODAY     (1–10)
  - on_call_load: 0 / 0.6 / 1.2 (matches wizard's None/A bit/Heavily)
"""

from __future__ import annotations
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Event taxonomy (effects in per-day deltas)
# ---------------------------------------------------------------------------
EVENT_TYPES = [
    "deadline_crunch", "reorg", "layoff", "on_call",
    "pto", "recognition", "personal_shock",
]

# Daily deltas applied to observed signals while the event is active.
EVENT_EFFECTS: dict[str, dict[str, float]] = {
    "deadline_crunch": {"hours": +2.0, "sleep": -0.6, "stress": +1.5, "deadline_pressure": +1.5},
    "reorg":           {"stress": +1.0, "mgr_support": -0.8, "mood": -0.5},
    "layoff":          {"stress": +1.5, "peer_support": -1.0, "mood": -1.0, "deadline_pressure": +0.5},
    "on_call":         {"hours": +1.0, "sleep": -0.4, "stress": +0.5},
    "pto":             {"hours": -8.0, "sleep": +1.0, "mood": +0.5, "stress": -0.5},
    "recognition":     {"mood": +0.8, "mgr_support": +0.6},
    "personal_shock":  {"mood": -1.0, "sleep": -0.7, "stress": +0.8},
}

# Min/max duration in DAYS per event.
EVENT_DURATION: dict[str, tuple[int, int]] = {
    "deadline_crunch": (4, 14),
    "reorg":           (14, 42),
    "layoff":          (21, 60),
    "on_call":         (1, 5),
    "pto":             (2, 10),
    "recognition":     (1, 1),
    "personal_shock":  (3, 14),
}

# Per-person-day probability that a given event begins.
# Roughly (old weekly rate) / 7 so a person sees a deadline_crunch
# every ~16 weeks, a reorg every ~year-ish, a layoff every ~3 years.
EVENT_SPAWN: dict[str, float] = {
    "deadline_crunch": 0.010,
    "reorg":           0.002,
    "layoff":          0.001,
    "on_call":         0.015,
    "pto":             0.008,
    "recognition":     0.006,
    "personal_shock":  0.004,
}


# ---------------------------------------------------------------------------
# Signal ranges
# ---------------------------------------------------------------------------
RAW_COLS = ["hours", "sleep", "mood", "stress", "mgr_support",
            "peer_support", "deadline_pressure", "on_call_load"]

CLAMP = {
    "hours": (0, 16), "sleep": (3, 11),
    "mood": (1, 10), "stress": (1, 10),
    "mgr_support": (1, 10), "peer_support": (1, 10),
    "deadline_pressure": (1, 10), "on_call_load": (0, 1.5),
}


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------
def generate(n_people: int = 120, n_days: int = 180, seed: int = 42,
             # Backwards-compat alias so old call sites still work
             n_teams: int | None = None, n_weeks: int | None = None,
             ) -> pd.DataFrame:
    """Generate a synthetic daily-check-in dataframe.

    n_people: how many simulated users.
    n_days:   how many days of history per user.

    Older callers may pass n_teams/n_weeks — we treat those as aliases
    (1 team == 1 person, 1 week == 7 days) so nothing breaks.
    """
    if n_teams is not None:
        n_people = n_teams
    if n_weeks is not None:
        n_days = n_weeks * 7

    rng = np.random.default_rng(seed)
    rows = []

    for person_id in range(n_people):
        # Stable per-person baseline.
        base = {
            "hours":             rng.normal(8.0, 1.0),
            "sleep":             rng.normal(7.0, 0.6),
            "mood":              rng.normal(7.0, 0.7),
            "stress":            rng.normal(4.5, 0.8),
            "mgr_support":       rng.normal(7.0, 0.9),
            "peer_support":      rng.normal(7.0, 0.7),
            "deadline_pressure": rng.normal(4.0, 0.8),
            "on_call_load":      rng.normal(0.2, 0.1),
        }
        R = float(rng.normal(0, 0.3))           # latent reservoir
        active: list[dict] = []                  # currently-running events

        for day in range(n_days):
            # Spawn new events for today.
            for ev in EVENT_TYPES:
                if rng.random() < EVENT_SPAWN[ev]:
                    dmin, dmax = EVENT_DURATION[ev]
                    dur = int(rng.integers(dmin, dmax + 1))
                    active.append({"type": ev, "end_day": day + dur})

            # Aggregate effects from active events.
            agg = {c: 0.0 for c in RAW_COLS}
            current = []
            for e in active:
                if e["end_day"] > day:
                    current.append(e["type"])
                    for k, v in EVENT_EFFECTS[e["type"]].items():
                        agg[k] += v
            active = [e for e in active if e["end_day"] > day]

            # Observed signals (noisier on the daily scale than weekly,
            # since you don't average over a week of work).
            obs = {
                "hours":             base["hours"] + agg["hours"] + rng.normal(0, 1.0),
                "sleep":             base["sleep"] + agg["sleep"] + rng.normal(0, 0.5),
                "mood":              base["mood"]  + agg["mood"]  + rng.normal(0, 0.6),
                "stress":            base["stress"] + agg["stress"] + rng.normal(0, 0.6),
                "mgr_support":       base["mgr_support"] + agg["mgr_support"] + rng.normal(0, 0.5),
                "peer_support":      base["peer_support"] + agg["peer_support"] + rng.normal(0, 0.5),
                "deadline_pressure": base["deadline_pressure"] + agg["deadline_pressure"] + rng.normal(0, 0.4),
                "on_call_load":      max(0.0, base["on_call_load"]
                                          + (0.6 if "on_call" in current else 0.0)
                                          + rng.normal(0, 0.05)),
            }
            for c, (lo, hi) in CLAMP.items():
                obs[c] = float(np.clip(obs[c], lo, hi))

            # --- Latent reservoir update (drives the label) -----------
            # Daily-scale physics: pressure/recovery numbers measured in
            # "deviations from a healthy baseline day", reservoir decays
            # slowly (a bad Monday still echoes on Wednesday).
            pressure = ((obs["hours"] - 8) / 2.0
                        + (obs["stress"] - 5) / 3.0
                        + (obs["deadline_pressure"] - 4) / 3.0
                        - (obs["mood"] - 6) / 4.0)
            recovery = ((obs["sleep"] - 7) / 1.5
                        + (obs["mgr_support"] - 6) / 4.0
                        + (obs["peer_support"] - 6) / 5.0
                        + (1.5 if "pto" in current else 0.0))
            R = 0.97 * R + 0.04 * (pressure - 0.6 * recovery) + float(rng.normal(0, 0.08))

            # Label: did the user feel burned-out *today*?
            # Intercept -1.0 gives ~10-13% positive days under the
            # baseline distribution above.
            p = 1.0 / (1.0 + np.exp(-(R - 1.0)))
            label = int(rng.random() < p)

            rows.append({
                "person_id": person_id,
                "team_id": person_id,         # kept for old consumers
                "day": day,
                "week": day // 7,             # convenience for grouping
                **obs,
                "events": "|".join(sorted(set(current))),
                "burnout": label,
                "_reservoir": R, "_p": float(p),
            })

    return pd.DataFrame(rows)


# --- Engineered-feature configuration --------------------------------------
DELTA_COLS = ["hours", "stress", "sleep", "mood", "deadline_pressure"]
STD_COLS   = ["hours", "stress", "sleep", "mood"]
SLOPE_COLS = ["hours", "stress"]

# Events whose "happened in last 14 days" indicator the model sees.
RECENT_EVENT_FLAGS = [
    ("layoff",   "layoff"),
    ("reorg",    "reorg"),
    ("deadline", "deadline_crunch"),
]

# Rolling windows in DAYS.
SHORT_WINDOW = 7    # ~ one work-week
LONG_WINDOW  = 28   # ~ one month
EVENT_WINDOW = 14   # ~ two weeks of "did this happen recently?"
PTO_CAP_DAYS = 60   # cap on "days since last PTO"


def _slope(arr: np.ndarray) -> float:
    """Least-squares slope of `arr` against [0, 1, ..., len-1]."""
    n = len(arr)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    return float(np.polyfit(x, arr, 1)[0])


def _days_since_pto(events_series: pd.Series) -> pd.Series:
    """Days since 'pto' last appeared in this person's events string,
    capped at PTO_CAP_DAYS. Default = cap if never seen — treat
    'unknown' as 'overdue', the conservative direction."""
    out, last_pto = [], None
    for i, ev in enumerate(events_series.values):
        if isinstance(ev, str) and "pto" in ev:
            last_pto = i
        out.append(float(PTO_CAP_DAYS) if last_pto is None
                   else float(min(PTO_CAP_DAYS, i - last_pto)))
    return pd.Series(out, index=events_series.index)


def _group_key(df: pd.DataFrame) -> str:
    """Pick whichever person-id column the dataframe actually carries."""
    return "person_id" if "person_id" in df.columns else "team_id"


def _time_key(df: pd.DataFrame) -> str:
    """Pick whichever time column the dataframe carries (day or week)."""
    return "day" if "day" in df.columns else "week"


def add_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    gk = _group_key(df)
    tk = _time_key(df)
    df = df.sort_values([gk, tk]).reset_index(drop=True)
    if "events" not in df.columns:
        df["events"] = ""

    g = df.groupby(gk)

    # Rolling means at the short and long horizons.
    for col in RAW_COLS:
        df[f"{col}_ma{SHORT_WINDOW}"] = g[col].transform(
            lambda s: s.rolling(SHORT_WINDOW, min_periods=1).mean())
        df[f"{col}_ma{LONG_WINDOW}"] = g[col].transform(
            lambda s: s.rolling(LONG_WINDOW, min_periods=1).mean())

    # Deltas: today minus 7-day rolling mean. Captures shocks the
    # smoothed mean hides.
    for col in DELTA_COLS:
        df[f"{col}_delta{SHORT_WINDOW}"] = df[col] - df[f"{col}_ma{SHORT_WINDOW}"]

    # Volatility (7-day rolling std). Chaos predicts burnout better than
    # the mean alone — averaging 9h with std 1 is fine; std 5 is thrash.
    for col in STD_COLS:
        df[f"{col}_std{SHORT_WINDOW}"] = (
            g[col].transform(lambda s: s.rolling(SHORT_WINDOW, min_periods=2).std())
                  .fillna(0.0)
        )

    # Trend slope: are stress/hours creeping up even if still in range?
    for col in SLOPE_COLS:
        df[f"{col}_slope{SHORT_WINDOW}"] = (
            g[col].transform(
                lambda s: s.rolling(SHORT_WINDOW, min_periods=2).apply(_slope, raw=True)
            ).fillna(0.0)
        )

    # Event-recency one-hots: did a layoff / reorg / deadline crunch
    # occur in the last 14 days?
    for short, full in RECENT_EVENT_FLAGS:
        df[f"had_{short}_{EVENT_WINDOW}d"] = (
            g["events"]
             .transform(lambda s, e=full:
                        s.fillna("").str.contains(e, regex=False)
                         .rolling(EVENT_WINDOW, min_periods=1).max())
             .astype(float)
        )

    # Days since last PTO — overdue rest is a recovery deficit.
    df["days_since_pto"] = g["events"].transform(_days_since_pto)

    # Interactions: capture compounding daily risks the linear model can't.
    # Scaled so a "normal day" (8h × stress 5) is around 2.
    df["hours_x_stress"] = (df["hours"] * df["stress"]) / 20.0
    # Gated interaction: only fires when hours > 10 AND sleep < 7.
    df["low_sleep_high_hours"] = (
        np.maximum(0.0, df["hours"] - 10.0)
        * np.maximum(0.0, 7.0 - df["sleep"])
    )

    return df


# Order matters — the dashboard / web scorer rebuilds the row in this order.
FEATURE_COLS: list[str] = (
    list(RAW_COLS)
    + [f"{c}_ma{SHORT_WINDOW}"  for c in RAW_COLS]
    + [f"{c}_ma{LONG_WINDOW}"   for c in RAW_COLS]
    + [f"{c}_delta{SHORT_WINDOW}" for c in DELTA_COLS]
    + [f"{c}_std{SHORT_WINDOW}"   for c in STD_COLS]
    + [f"{c}_slope{SHORT_WINDOW}" for c in SLOPE_COLS]
    + [f"had_{short}_{EVENT_WINDOW}d" for short, _ in RECENT_EVENT_FLAGS]
    + ["days_since_pto", "hours_x_stress", "low_sleep_high_hours"]
)


if __name__ == "__main__":
    df = generate()
    df = add_rolling_features(df)
    print(df.head())
    print(f"Shape: {df.shape}")
    print(f"Positive rate: {df['burnout'].mean():.3f}")
    print(f"Feature count: {len(FEATURE_COLS)}")
