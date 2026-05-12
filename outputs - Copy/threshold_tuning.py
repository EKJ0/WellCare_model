"""Pick an action threshold for the model.

A probability score is useless until you turn it into a decision:
  "Anyone with risk > X gets a 1:1 with their manager next week."
  "I follow up with the top 10 riskiest team-weeks each Monday."

This script reads scored_teams.csv (written by train.py) and shows
two views of the trade-off:

  PRECISION-AT-K:   if I only have bandwidth to follow up on the top K
                    team-weeks, what fraction will be true positives?
  THRESHOLD TABLE:  for various probability cutoffs, what precision /
                    recall / number-flagged would I get?

Lets you pick a threshold that matches your bandwidth and tolerance
for false alarms. Writes thresholds.csv for downstream tooling.
"""

from __future__ import annotations
from pathlib import Path
import json

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
SCORED = OUT / "scored_teams.csv"
SCORE_COL_PREFERENCE = ("risk_platt", "risk_isotonic", "risk_logreg", "risk_raw_gbt")


def bar(value: float, width: int = 22) -> str:
    n = max(0, min(width, int(round(value * width))))
    return "#" * n + "." * (width - n)


def main() -> None:
    if not SCORED.exists():
        raise SystemExit(
            f"{SCORED.name} not found. Run `python train.py` first.")
    df = pd.read_csv(SCORED)

    score_col = next((c for c in SCORE_COL_PREFERENCE if c in df.columns),
                     None)
    if score_col is None:
        raise SystemExit("No risk_* column in scored_teams.csv")

    y = df["burnout"].values.astype(int)
    p = df[score_col].values.astype(float)
    n = len(y)
    base_rate = float(y.mean())

    print("=" * 72)
    print(f"  Threshold tuning  (using {score_col})")
    print("=" * 72)
    print(f"  scored team-weeks : {n}")
    print(f"  base positive rate: {base_rate:.3f}  ({int(y.sum())} positives)")

    # --- Precision @ K -----------------------------------------------------
    print()
    print("PRECISION @ K  -  if you can only follow up on K team-weeks:")
    print(f"  {'K':<6} {'%':<6} {'TP':<5} {'precision':<10} {'recall':<8} "
          f"{'lift vs base':<14}")
    print("  " + "-" * 60)
    order = np.argsort(-p)
    sorted_y = y[order]
    fractions = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40]
    rows_pk = []
    for f in fractions:
        K = max(1, int(round(f * n)))
        tp = int(sorted_y[:K].sum())
        prec = tp / K
        rec = tp / max(1, int(y.sum()))
        lift = prec / base_rate if base_rate > 0 else float("nan")
        rows_pk.append({"K": K, "fraction": f, "true_positives": tp,
                        "precision": prec, "recall": rec, "lift": lift})
        print(f"  {K:<6} {f * 100:<6.1f} {tp:<5} {prec:<10.3f} {rec:<8.3f} "
              f"{lift:<6.2f}x")

    # --- Threshold table ---------------------------------------------------
    print()
    print("THRESHOLD TABLE  -  for various probability cutoffs:")
    print(f"  {'thr':<7} {'flagged':<8} {'TP':<5} {'FP':<5} "
          f"{'precision':<10} {'recall':<8} {'F1':<6}")
    print("  " + "-" * 60)
    thresholds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.75]
    rows_thr = []
    for thr in thresholds:
        pred = (p >= thr).astype(int)
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        flagged = tp + fp
        prec = tp / flagged if flagged else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        rows_thr.append({"threshold": thr, "flagged": flagged,
                         "true_positives": tp, "false_positives": fp,
                         "precision": prec, "recall": rec, "f1": f1})
        print(f"  {thr:<7.2f} {flagged:<8} {tp:<5} {fp:<5} "
              f"{prec:<10.3f} {rec:<8.3f} {f1:<6.3f}")

    # --- F1-optimal threshold ---------------------------------------------
    best = max(rows_thr, key=lambda r: r["f1"])
    print()
    print("Best F1 in the grid:")
    print(f"  threshold = {best['threshold']:.2f}  -> "
          f"precision={best['precision']:.3f}  recall={best['recall']:.3f}  "
          f"f1={best['f1']:.3f}  ({best['flagged']} flagged)")

    # --- Suggested operating points ---------------------------------------
    print()
    print("SUGGESTED OPERATING POINTS:")
    suggest = [
        ("Aggressive  (high recall, low precision)",
         [r for r in rows_thr if r["recall"] >= 0.70][0:1]),
        ("Balanced    (best F1)", [best]),
        ("Conservative (high precision, low recall)",
         [r for r in rows_thr if r["precision"] >= max(0.4, base_rate * 4)][0:1]),
    ]
    for label, candidates in suggest:
        if not candidates:
            continue
        r = candidates[0]
        print(f"  {label}")
        print(f"     threshold {r['threshold']:.2f}  ->  "
              f"flag {r['flagged']} of {n}  "
              f"({r['precision']*100:.0f}% precision, "
              f"{r['recall']*100:.0f}% recall)")

    # --- Save --------------------------------------------------------------
    pd.DataFrame(rows_pk).to_csv(OUT / "thresholds_at_k.csv", index=False)
    pd.DataFrame(rows_thr).to_csv(OUT / "thresholds.csv", index=False)
    (OUT / "thresholds_summary.json").write_text(json.dumps({
        "score_col": score_col,
        "base_rate": base_rate,
        "best_f1":   best,
    }, indent=2))
    print("\nWrote: thresholds.csv, thresholds_at_k.csv, thresholds_summary.json")


if __name__ == "__main__":
    main()
