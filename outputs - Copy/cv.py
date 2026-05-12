"""5-fold time-series cross-validation (forward chaining).

For time-series, ordinary k-fold leaks future into past. Forward
chaining trains on weeks [0..t], evaluates on weeks (t..t+k], then
extends the train set and repeats. This gives a realistic estimate
of how the model would perform week-to-week in production.

Reports mean +- std across folds for both LR and GBT, and prints a
per-fold table so you can see whether one bad week is dragging the
mean (very common in burnout-style data with seasonal events).

Usage:
    python cv.py             # 5-fold, default config
    python cv.py --folds 8   # more folds (smaller test windows)
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scenarios import generate, add_rolling_features, FEATURE_COLS
from models import (
    LogisticRegression, GradientBoostedClassifier,
    PlattScaling, roc_auc, pr_auc, brier_score,
)

OUT = Path(__file__).resolve().parent


def standardize(X_train: np.ndarray, *others: np.ndarray):
    mu = X_train.mean(axis=0)
    sigma = X_train.std(axis=0) + 1e-6
    out = [(X_train - mu) / sigma]
    for X in others:
        out.append((X - mu) / sigma)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--n-teams", type=int, default=120)
    ap.add_argument("--n-weeks", type=int, default=44)
    args = ap.parse_args()

    print("Generating data...")
    df = add_rolling_features(generate(
        n_teams=args.n_teams, n_weeks=args.n_weeks, seed=42))
    wmax = int(df["week"].max())

    # Forward-chaining splits: train [0..cuts[i]], test (cuts[i]..cuts[i+1]]
    # Initial train must be at least 30% of weeks so rolling features warm up.
    initial = max(8, int(0.30 * wmax))
    cuts = np.linspace(initial, wmax, args.folds + 1).astype(int)

    rows = []
    print(f"\nForward-chaining CV: {args.folds} folds, "
          f"initial train = {initial} weeks, max week = {wmax}\n")
    print(f"  {'fold':<5} {'tr_weeks':<8} {'te_weeks':<8} "
          f"{'lr_brier':<10} {'lr_roc':<8} "
          f"{'gbt_brier':<10} {'gbt_roc':<8} {'gbt_pr':<8}")
    print("  " + "-" * 70)

    for i in range(args.folds):
        train_end = int(cuts[i])
        test_end  = int(cuts[i + 1])
        train = df[df["week"] <= train_end]
        test  = df[(df["week"] > train_end) & (df["week"] <= test_end)]
        # Use the last 15% of train as a small val for GBT early stopping.
        val_start = max(train_end - max(2, (train_end - 1) // 6), 1)
        val   = train[train["week"] >  val_start]
        train = train[train["week"] <= val_start]

        if len(train) < 10 or len(val) < 5 or len(test) < 5:
            continue

        Xtr = train[FEATURE_COLS].values.astype(float); ytr = train["burnout"].values.astype(int)
        Xv  = val[FEATURE_COLS].values.astype(float);   yv  = val["burnout"].values.astype(int)
        Xte = test[FEATURE_COLS].values.astype(float);  yte = test["burnout"].values.astype(int)

        Xtr_s, Xte_s = standardize(Xtr, Xte)
        lr = LogisticRegression(lr=0.1, n_iter=1500).fit(Xtr_s, ytr)
        p_lr = lr.predict_proba(Xte_s)

        gbt = GradientBoostedClassifier(
            n_estimators=200, max_depth=3, learning_rate=0.05,
            subsample=0.8, seed=i,
        )
        gbt.fit(Xtr, ytr, X_val=Xv, y_val=yv, early_stopping_rounds=15)
        p_gbt = gbt.predict_proba(Xte)

        row = {
            "fold": i + 1,
            "tr_weeks": train_end,
            "te_weeks": test_end - train_end,
            "lr_brier":  brier_score(yte, p_lr),
            "lr_roc":    float(roc_auc(yte, p_lr)),
            "lr_pr":     float(pr_auc(yte, p_lr)),
            "gbt_brier": brier_score(yte, p_gbt),
            "gbt_roc":   float(roc_auc(yte, p_gbt)),
            "gbt_pr":    float(pr_auc(yte, p_gbt)),
            "test_pos_rate": float(yte.mean()),
        }
        rows.append(row)
        print(f"  {row['fold']:<5} {row['tr_weeks']:<8} {row['te_weeks']:<8} "
              f"{row['lr_brier']:<10.4f} {row['lr_roc']:<8.3f} "
              f"{row['gbt_brier']:<10.4f} {row['gbt_roc']:<8.3f} "
              f"{row['gbt_pr']:<8.3f}")

    if not rows:
        print("\nNo valid folds. Try fewer folds or more weeks.")
        return

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "cv_results.csv", index=False)

    print("\nSummary (mean +- std across folds):")
    for col in ["lr_brier", "lr_roc", "lr_pr", "gbt_brier", "gbt_roc", "gbt_pr"]:
        m, s = out[col].mean(), out[col].std()
        print(f"  {col:<12} {m:.4f} +- {s:.4f}")

    summary = {
        "n_folds": len(rows),
        "lr_brier_mean":  float(out["lr_brier"].mean()),
        "lr_brier_std":   float(out["lr_brier"].std()),
        "gbt_brier_mean": float(out["gbt_brier"].mean()),
        "gbt_brier_std":  float(out["gbt_brier"].std()),
        "lr_roc_mean":    float(out["lr_roc"].mean()),
        "gbt_roc_mean":   float(out["gbt_roc"].mean()),
    }
    (OUT / "cv_summary.json").write_text(json.dumps(summary, indent=2))

    # Verdict for the impatient
    delta = summary["lr_brier_mean"] - summary["gbt_brier_mean"]
    print(f"\nVerdict: ", end="")
    if abs(delta) < summary["lr_brier_std"] + summary["gbt_brier_std"]:
        print("LR and GBT are within noise of each other across folds.")
        print("  Pick LR (simpler, faster, more interpretable).")
    elif delta > 0:
        print(f"GBT beats LR by {delta:.4f} Brier on average — use GBT.")
    else:
        print(f"LR beats GBT by {-delta:.4f} Brier on average — use LR.")

    print("\nWrote: cv_results.csv, cv_summary.json")


if __name__ == "__main__":
    main()
