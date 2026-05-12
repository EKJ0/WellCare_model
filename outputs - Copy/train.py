"""Training pipeline for the WellCare daily burnout-risk model.

Steps:
1. Generate synthetic per-person-per-day data with event-driven signals.
2. Build rolling-window features (7-day + 28-day means, deltas, std, slope).
3. Time-ordered train/val/test split on the `day` axis (no future leakage).
4. Fit logistic-regression baseline + gradient-boosted trees.
5. Calibrate GBT probabilities with Platt + Isotonic on val set.
6. Save metrics, feature importance, scored test set, model bundle."""

from __future__ import annotations
import datetime as _dt
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from scenarios import generate, add_rolling_features, FEATURE_COLS
from models import (
    LogisticRegression, GradientBoostedClassifier,
    IsotonicRegression, PlattScaling,
    roc_auc, pr_auc, brier_score,
)


OUT = Path(__file__).resolve().parent
BUNDLES_DIR = OUT / "bundles"  # versioned, never overwritten


def time_split(df: pd.DataFrame, train_end: float = 0.7, val_end: float = 0.85
               ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split chronologically on whichever time column the df carries.

    Daily data uses `day`; legacy weekly frames use `week`. Either works."""
    col = "day" if "day" in df.columns else "week"
    tmax = int(df[col].max())
    t1 = int(tmax * train_end)
    t2 = int(tmax * val_end)
    train = df[df[col] <= t1].copy()
    val   = df[(df[col] > t1) & (df[col] <= t2)].copy()
    test  = df[df[col] > t2].copy()
    return train, val, test


def standardize(train_X: np.ndarray, *others: np.ndarray):
    mu = train_X.mean(axis=0)
    sigma = train_X.std(axis=0) + 1e-6
    out = [(train_X - mu) / sigma]
    for X in others:
        out.append((X - mu) / sigma)
    return out, (mu, sigma)


def main() -> None:
    print("Generating synthetic daily check-in data...")
    # 120 people × 180 days = 21,600 daily rows.
    df = generate(n_people=120, n_days=180, seed=42)
    df = add_rolling_features(df)
    pos_rate = float(df["burnout"].mean())
    print(f"  shape={df.shape}  overall positive rate={pos_rate:.3f}")

    train, val, test = time_split(df)
    print(f"  splits: train={len(train)}  val={len(val)}  test={len(test)}")

    Xtr = train[FEATURE_COLS].values.astype(float)
    ytr = train["burnout"].values.astype(int)
    Xv  = val[FEATURE_COLS].values.astype(float)
    yv  = val["burnout"].values.astype(int)
    Xte = test[FEATURE_COLS].values.astype(float)
    yte = test["burnout"].values.astype(int)

    (Xtr_s, Xv_s, Xte_s), (mu, sigma) = standardize(Xtr, Xv, Xte)

    # --- Logistic regression baseline ----------------------------------------
    print("\nFitting logistic regression baseline...")
    lr = LogisticRegression(lr=0.1, n_iter=2000, l2=1e-3).fit(Xtr_s, ytr)
    p_te_lr = lr.predict_proba(Xte_s)
    print(f"  test ROC-AUC={roc_auc(yte, p_te_lr):.3f}  "
          f"PR-AUC={pr_auc(yte, p_te_lr):.3f}  "
          f"Brier={brier_score(yte, p_te_lr):.3f}")

    # --- Gradient boosted trees (early stopping on val) ----------------------
    print("\nFitting gradient-boosted trees...")
    gbt = GradientBoostedClassifier(
        n_estimators=120, max_depth=3, learning_rate=0.05,
        subsample=0.8, seed=0,
    )
    gbt.fit(Xtr, ytr, X_val=Xv, y_val=yv, early_stopping_rounds=15)
    print(f"  trees retained: {len(gbt.trees)}")
    p_v_gbt   = gbt.predict_proba(Xv)
    p_te_raw  = gbt.predict_proba(Xte)

    # --- Calibration: Platt vs Isotonic on val -------------------------------
    # Isotonic is left in for comparison only. With ~88 positives in val it
    # tends to overfit; Platt's two parameters are more stable.
    print("\nCalibrating GBT probabilities on val (Platt + isotonic)...")
    platt = PlattScaling().fit(p_v_gbt, yv)
    iso = IsotonicRegression().fit(p_v_gbt, yv)
    p_te_platt = platt.transform(p_te_raw)
    p_te_iso = iso.transform(p_te_raw)

    metrics = {
        "positive_rate_overall": pos_rate,
        "n_train": int(len(train)), "n_val": int(len(val)), "n_test": int(len(test)),
        "test_positive_rate": float(yte.mean()),
        "logreg": {
            "roc_auc": float(roc_auc(yte, p_te_lr)),
            "pr_auc":  float(pr_auc(yte, p_te_lr)),
            "brier":   brier_score(yte, p_te_lr),
        },
        "gbt": {
            "roc_auc":         float(roc_auc(yte, p_te_raw)),
            "pr_auc":          float(pr_auc(yte, p_te_raw)),
            "brier":           brier_score(yte, p_te_raw),
            "brier_platt":     brier_score(yte, p_te_platt),
            "brier_isotonic":  brier_score(yte, p_te_iso),
            "n_trees":         len(gbt.trees),
        },
    }
    print("\nTest metrics:")
    print(json.dumps(metrics, indent=2))

    # --- Feature importance, scored test set --------------------------------
    imp = gbt.feature_importance(len(FEATURE_COLS))
    fi = sorted(zip(FEATURE_COLS, imp.tolist()), key=lambda x: -x[1])

    scored = test.copy()
    scored["risk_raw_gbt"]    = p_te_raw
    scored["risk_platt"]      = p_te_platt
    scored["risk_isotonic"]   = p_te_iso
    scored["risk_logreg"]     = p_te_lr

    # --- Persist artifacts ---------------------------------------------------
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    pd.DataFrame(fi, columns=["feature", "importance"]).to_csv(
        OUT / "feature_importance.csv", index=False)
    df.to_csv(OUT / "synthetic_data.csv", index=False)
    scored.to_csv(OUT / "scored_teams.csv", index=False)

    bundle = {
        "feature_cols": FEATURE_COLS,
        "standardization": {"mu": mu.tolist(), "sigma": sigma.tolist()},
        "logreg":   lr.to_dict(),
        "gbt":      gbt.to_dict(),
        "platt":    platt.to_dict(),
        "isotonic": iso.to_dict(),
        "metrics":  metrics,
    }
    # --- Versioned bundle write ---------------------------------------------
    # Two artifacts:
    #   1. bundles/model_bundle_<UTC-iso>.json  — never overwritten
    #   2. model_bundle.json                    — copy of the latest, used
    #                                             by predict.py and the web app
    BUNDLES_DIR.mkdir(exist_ok=True)
    stamp = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    bundle["trained_at"] = stamp
    versioned = BUNDLES_DIR / f"model_bundle_{stamp}.json"
    versioned.write_text(json.dumps(bundle))
    shutil.copy(versioned, OUT / "model_bundle.json")
    # Compact pointer so other tools can find the latest by name.
    (BUNDLES_DIR / "LATEST.txt").write_text(versioned.name)

    print(f"\nWrote: metrics.json, feature_importance.csv, synthetic_data.csv, "
          f"scored_teams.csv, model_bundle.json")
    print(f"       (versioned copy: bundles/{versioned.name})")


if __name__ == "__main__":
    main()
