"""Sanity-check the trained model on the scored test set.

Prints:
  1. Top features by GBT importance (with bars).
  2. Top-20 highest-risk team-weeks with the signals that should explain
     the score (hours, sleep, mood, stress, deadline pressure, support,
     recent events). If the highest-risk rows look healthy, the model is
     wrong; if they look stressed and event-laden, it's working.

Note: this file is named inspect_model.py (not inspect.py) to avoid
shadowing Python's stdlib `inspect` module, which pandas imports."""

from __future__ import annotations
from pathlib import Path
import pandas as pd

OUT = Path(__file__).resolve().parent
RANK_COL = "risk_platt"  # train.py writes risk_platt, risk_isotonic, risk_logreg, risk_raw_gbt


def bar(x: float, width: int = 30) -> str:
    n = max(0, min(width, int(round(x * width))))
    return "#" * n + "." * (width - n)


def main() -> None:
    fi = pd.read_csv(OUT / "feature_importance.csv")
    print("=" * 70)
    print("GBT FEATURE IMPORTANCE  (top 12)")
    print("=" * 70)
    fmax = float(fi["importance"].max()) or 1.0
    for _, r in fi.head(12).iterrows():
        print(f"  {r['feature']:<25} {bar(r['importance']/fmax):<32}  {r['importance']:.3f}")

    scored = pd.read_csv(OUT / "scored_teams.csv")
    rank_col = RANK_COL if RANK_COL in scored.columns else "risk_raw_gbt"
    top = scored.sort_values(rank_col, ascending=False).head(20)

    cols = ["team_id", "week", rank_col, "burnout",
            "hours", "sleep", "mood", "stress",
            "deadline_pressure", "mgr_support", "events"]
    cols = [c for c in cols if c in top.columns]

    pd.options.display.width = 200
    pd.options.display.max_colwidth = 28
    pd.options.display.float_format = lambda v: f"{v:.2f}"

    print()
    print("=" * 70)
    print(f"TOP 20 BY {rank_col}  (burnout=1 is a true positive)")
    print("=" * 70)
    print(top[cols].to_string(index=False))

    hits = int(top["burnout"].sum())
    base_rate = float(scored["burnout"].mean())
    expected = base_rate * len(top)
    print(f"\nTrue positives in top 20: {hits}/20  "
          f"(expected at base rate {base_rate:.3f}: {expected:.1f})")
    if hits >= 2 * expected:
        print("  -> Top-of-list is meaningfully enriched. Model is working.")
    else:
        print("  -> Enrichment is weak; the ranker isn't separating well.")


if __name__ == "__main__":
    main()
