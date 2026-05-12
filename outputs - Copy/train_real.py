"""Train the burnout model on real check-in data.

Same pipeline as train.py, but the data source is `load_real.from_csv()`
instead of `scenarios.generate()`. Adds two low-data guardrails since
real check-in datasets start small:

  --blend N : also generate N synthetic teams and concatenate them with
              the real data before training. Useful in the first months
              when you have <10 real teams. The model bundle is tagged
              with `data_source` so you know how it was trained.

  --min-rows / --min-positives : refuse to train if the data is too
              small to learn anything meaningful. Default 80 rows and 10
              positives — below that you'd just be memorizing noise.

Output: model_bundle_real.json (separate from the synthetic-trained
model_bundle.json so you can A/B and roll back). Set predict.py's
BUNDLE constant to "model_bundle_real.json" to score against the real
model."""

from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scenarios import generate, add_rolling_features, FEATURE_COLS
from models import (
    LogisticRegression, GradientBoostedClassifier,
    PlattScaling, IsotonicRegression,
    roc_auc, pr_auc, brier_score,
)
from train import time_split, standardize
import load_real

OUT = Path(__file__).resolve().parent
BUNDLE_PATH = OUT / "model_bundle_real.json"
METRICS_PATH = OUT / "metrics_real.json"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", default=str(load_real.DEFAULT_PATH),
                    help="path to checkins.csv (or Google Form export)")
    ap.add_argument("--blend", type=int, default=0,
                    help="add N synthetic teams to thicken the dataset")
    ap.add_argument("--min-rows", type=int, default=80,
                    help="refuse to train if real rows < this")
    ap.add_argument("--min-positives", type=int, default=10,
                    help="refuse to train if labeled positives < this")
    args = ap.parse_args()

    real = load_real.from_csv(args.csv)
    summary = load_real.summary(real)

    labeled = real.dropna(subset=["burnout"]).copy()
    n_rows = len(labeled)
    n_pos = int(labeled["burnout"].sum())

    if n_rows < args.min_rows or n_pos < args.min_positives:
        print()
        print("=" * 60)
        print(" NOT ENOUGH DATA TO TRAIN A REAL MODEL YET")
        print("=" * 60)
        print(f"  Have:    {n_rows} labeled rows, {n_pos} positives")
        print(f"  Need:    >= {args.min_rows} rows AND >= {args.min_positives} positives")
        print()
        print("  Options:")
        print("   1. Keep collecting via `python checkin.py` and re-run later.")
        print(f"   2. Train with synthetic blend: `python train_real.py --blend 60`")
        print("      (uses your real data + 60 synthetic teams; model bundle")
        print("       tagged so you know it's hybrid.)")
        if args.blend == 0:
            return

    # --- Optional synthetic blend ----------------------------------------
    if args.blend > 0:
        print(f"\nBlending in {args.blend} synthetic people (180 days each)...")
        synth = generate(n_people=args.blend, n_days=180, seed=1)
        synth["person_id"] = "synth_" + synth["person_id"].astype(str)
        synth["team_id"]   = synth["person_id"]
        synth["date"]      = pd.NaT  # no real date for synthetic rows
        # Keep just the columns that exist on both sides.
        common = [c for c in real.columns if c in synth.columns]
        df = pd.concat([labeled[common], synth[common]], ignore_index=True)
        data_source = f"real({n_rows})+synthetic({len(synth)})"
    else:
        df = labeled
        data_source = f"real({n_rows})"

    print(f"\nData source: {data_source}")
    df = add_rolling_features(df)

    # --- Same time-ordered split as train.py -----------------------------
    train, val, test = time_split(df)
    print(f"  splits: train={len(train)}  val={len(val)}  test={len(test)}")
    if min(len(train), len(val), len(test)) < 5:
        print("  !! one of the splits is tiny; metrics will be noisy.")

    Xtr = train[FEATURE_COLS].values.astype(float); ytr = train["burnout"].values.astype(int)
    Xv  = val[FEATURE_COLS].values.astype(float);   yv  = val["burnout"].values.astype(int)
    Xte = test[FEATURE_COLS].values.astype(float);  yte = test["burnout"].values.astype(int)

    # Replace any NaN feature values (real data is messier) with column
    # medians from train; this matches what a production scorer would do.
    medians = np.nanmedian(Xtr, axis=0)
    for X in (Xtr, Xv, Xte):
        idx = np.where(np.isnan(X))
        X[idx] = np.take(medians, idx[1])

    (Xtr_s, Xv_s, Xte_s), (mu, sigma) = standardize(Xtr, Xv, Xte)

    # --- Logistic regression ---------------------------------------------
    print("\nFitting logistic regression baseline...")
    lr = LogisticRegression(lr=0.1, n_iter=2000, l2=1e-3).fit(Xtr_s, ytr)
    p_te_lr = lr.predict_proba(Xte_s)
    print(f"  test ROC-AUC={roc_auc(yte, p_te_lr):.3f}  "
          f"PR-AUC={pr_auc(yte, p_te_lr):.3f}  Brier={brier_score(yte, p_te_lr):.3f}")

    # --- GBT --------------------------------------------------------------
    print("\nFitting gradient-boosted trees...")
    gbt = GradientBoostedClassifier(n_estimators=400, max_depth=2,
                                    learning_rate=0.02, subsample=0.8, seed=0)
    gbt.fit(Xtr, ytr, X_val=Xv, y_val=yv, early_stopping_rounds=20)
    p_v_gbt = gbt.predict_proba(Xv)
    p_te_raw = gbt.predict_proba(Xte)
    print(f"  trees retained: {len(gbt.trees)}")

    # --- Calibration (Platt is more stable on small val) ------------------
    platt = PlattScaling().fit(p_v_gbt, yv)
    iso   = IsotonicRegression().fit(p_v_gbt, yv)
    p_te_platt = platt.transform(p_te_raw)
    p_te_iso   = iso.transform(p_te_raw)

    metrics = {
        "data_source": data_source,
        "data_summary": summary,
        "test_positive_rate": float(yte.mean()),
        "logreg": {
            "roc_auc": float(roc_auc(yte, p_te_lr)),
            "pr_auc":  float(pr_auc(yte, p_te_lr)),
            "brier":   brier_score(yte, p_te_lr),
        },
        "gbt": {
            "roc_auc":        float(roc_auc(yte, p_te_raw)),
            "pr_auc":         float(pr_auc(yte, p_te_raw)),
            "brier":          brier_score(yte, p_te_raw),
            "brier_platt":    brier_score(yte, p_te_platt),
            "brier_isotonic": brier_score(yte, p_te_iso),
            "n_trees":        len(gbt.trees),
        },
    }
    print("\nTest metrics:")
    print(json.dumps(metrics, indent=2))

    bundle = {
        "data_source": data_source,
        "feature_cols": FEATURE_COLS,
        "standardization": {"mu": mu.tolist(), "sigma": sigma.tolist()},
        "logreg":   lr.to_dict(),
        "gbt":      gbt.to_dict(),
        "platt":    platt.to_dict(),
        "isotonic": iso.to_dict(),
        "metrics":  metrics,
    }
    BUNDLE_PATH.write_text(json.dumps(bundle))
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    print(f"\nWrote: {BUNDLE_PATH.name}, {METRICS_PATH.name}")
    print("\nTo use this model in predict.py, change the BUNDLE constant at")
    print("the top of predict.py from 'model_bundle.json' to "
          f"'{BUNDLE_PATH.name}'.")


if __name__ == "__main__":
    main()
