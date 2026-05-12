"""GBT hyperparameter sweep.

Uses the *same* time-ordered train/val/test split as train.py. For each
config, fits on train (with early stopping on val) and reports val Brier
plus test ROC-AUC / PR-AUC / Brier. Final ranking is by val Brier — test
metrics are reported but never used for selection (no leakage)."""

from __future__ import annotations
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scenarios import generate, add_rolling_features, FEATURE_COLS
from models import GradientBoostedClassifier, roc_auc, pr_auc, brier_score
from train import time_split


OUT = Path(__file__).resolve().parent

# Grid: shallow + many trees + small lr is the standard recipe for a near-
# linear target. The wider the grid, the longer this runs — ~30 fits below.
GRID = {
    "max_depth":     [2, 3, 4],
    "n_estimators":  [200, 400, 800],
    "learning_rate": [0.02, 0.05, 0.1],
    "subsample":     [0.8],
}


def main() -> None:
    print("Generating data...")
    df = add_rolling_features(generate(n_people=160, n_days=240, seed=42))
    train, val, test = time_split(df)
    Xtr = train[FEATURE_COLS].values.astype(float); ytr = train["burnout"].values.astype(int)
    Xv  = val[FEATURE_COLS].values.astype(float);   yv  = val["burnout"].values.astype(int)
    Xte = test[FEATURE_COLS].values.astype(float);  yte = test["burnout"].values.astype(int)

    keys = list(GRID.keys())
    combos = list(itertools.product(*[GRID[k] for k in keys]))
    print(f"Sweeping {len(combos)} configs...\n")

    rows = []
    for i, vals in enumerate(combos, 1):
        cfg = dict(zip(keys, vals))
        gbt = GradientBoostedClassifier(seed=0, **cfg)
        gbt.fit(Xtr, ytr, X_val=Xv, y_val=yv, early_stopping_rounds=20)

        p_v  = gbt.predict_proba(Xv)
        p_te = gbt.predict_proba(Xte)
        row = {
            **cfg,
            "trees_kept":  len(gbt.trees),
            "val_brier":   brier_score(yv,  p_v),
            "test_brier":  brier_score(yte, p_te),
            "test_roc":    float(roc_auc(yte, p_te)),
            "test_pr":     float(pr_auc(yte, p_te)),
        }
        rows.append(row)
        print(f"[{i:2d}/{len(combos)}] depth={cfg['max_depth']} "
              f"n={cfg['n_estimators']:>3} lr={cfg['learning_rate']:<5} "
              f"-> kept={row['trees_kept']:>3}  val_brier={row['val_brier']:.4f}  "
              f"test_brier={row['test_brier']:.4f}  roc={row['test_roc']:.3f}")

    df_out = pd.DataFrame(rows).sort_values("val_brier").reset_index(drop=True)
    df_out.to_csv(OUT / "tune_results.csv", index=False)

    best = df_out.iloc[0].to_dict()
    print("\nBest by val Brier:")
    print(json.dumps(best, indent=2, default=str))

    # Compare against the baseline numbers from the last train.py run.
    metrics_path = OUT / "metrics.json"
    if metrics_path.exists():
        baseline = json.loads(metrics_path.read_text())
        print("\nBaseline (current train.py):")
        print(f"  logreg   test_brier={baseline['logreg']['brier']:.4f}  "
              f"roc={baseline['logreg']['roc_auc']:.3f}")
        print(f"  gbt(raw) test_brier={baseline['gbt']['brier']:.4f}  "
              f"roc={baseline['gbt']['roc_auc']:.3f}")

    print("\nWrote: tune_results.csv")


if __name__ == "__main__":
    main()
