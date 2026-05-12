"""End-to-end smoke test for the burnout-risk pipeline.

Runs in <30s, no test framework needed. Asserts that:
  1. Data generation + feature engineering work and shapes match.
  2. All three models (LR, GBT, Platt) fit and predict.
  3. ROC-AUC > 0.6 — the model isn't broken (random would be 0.5).
  4. Brier < 0.20 — predictions aren't wildly miscalibrated.
  5. predict.py can load a freshly-saved bundle and produce a number
     for the canned --demo cases.
  6. CSV round-trip: write a synthetic checkins.csv, read it back via
     load_real.from_csv(), get the same row count.
  7. Feature counts match between training and prediction (catches
     drift between scenarios.FEATURE_COLS and predict._build_features).

Run after editing scenarios.py / models.py / train.py / predict.py.
Exits 0 on pass, non-zero with a traceback on fail.
"""

from __future__ import annotations
import csv
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))

from scenarios import (
    generate, add_rolling_features, FEATURE_COLS, RAW_COLS, EVENT_TYPES,
)
from models import (
    LogisticRegression, GradientBoostedClassifier,
    PlattScaling, IsotonicRegression,
    roc_auc, pr_auc, brier_score,
)
from train import time_split, standardize


PASSED = 0
FAILED = 0


def check(name, cond, detail=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name}  {detail}")


# ---------------------------------------------------------------------------
def test_generation_and_features():
    print("\n[1] Data generation + feature engineering")
    df = generate(n_people=20, n_days=60, seed=7)
    check("generate produces rows", len(df) == 20 * 60, f"got {len(df)}")
    check("RAW_COLS present", all(c in df.columns for c in RAW_COLS))
    check("burnout column present", "burnout" in df.columns)
    check("burnout is 0/1", set(df["burnout"].unique()) <= {0, 1})

    df2 = add_rolling_features(df)
    check("FEATURE_COLS all populated",
          all(c in df2.columns for c in FEATURE_COLS),
          f"missing: {[c for c in FEATURE_COLS if c not in df2.columns]}")
    check("no NaN in feature columns",
          not df2[FEATURE_COLS].isna().any().any())
    check("event one-hots are 0/1",
          set(df2["had_layoff_14d"].unique()) <= {0.0, 1.0})


# ---------------------------------------------------------------------------
def test_models_fit_and_predict():
    print("\n[2] Models fit and produce sensible predictions")
    df = add_rolling_features(generate(n_people=60, n_days=120, seed=1))
    train, val, test = time_split(df)
    X_train = train[FEATURE_COLS].values.astype(float)
    y_train = train["burnout"].values.astype(int)
    X_val   = val[FEATURE_COLS].values.astype(float)
    y_val   = val["burnout"].values.astype(int)
    X_test  = test[FEATURE_COLS].values.astype(float)
    y_test  = test["burnout"].values.astype(int)

    (Xtr_s, Xv_s, Xte_s), _ = standardize(X_train, X_val, X_test)

    lr = LogisticRegression(n_iter=400).fit(Xtr_s, y_train)
    p_lr = lr.predict_proba(Xte_s)
    auc_lr = roc_auc(y_test, p_lr)
    brier_lr = brier_score(y_test, p_lr)
    check(f"LR ROC-AUC > 0.60 (got {auc_lr:.3f})", auc_lr > 0.60)
    check(f"LR Brier < 0.20 (got {brier_lr:.3f})", brier_lr < 0.20)

    gbt = GradientBoostedClassifier(n_estimators=40, max_depth=2, seed=0)
    gbt.fit(X_train, y_train, X_val=X_val, y_val=y_val)
    p_gbt = gbt.predict_proba(X_test)
    auc_gbt = roc_auc(y_test, p_gbt)
    check(f"GBT ROC-AUC > 0.55 (got {auc_gbt:.3f})", auc_gbt > 0.55)

    p_v = gbt.predict_proba(X_val)
    platt = PlattScaling().fit(p_v, y_val)
    p_cal = platt.transform(p_gbt)
    check("Platt outputs in (0,1)", float(p_cal.min()) > 0 and float(p_cal.max()) < 1)
    check("PR-AUC > base rate",
          pr_auc(y_test, p_lr) > float(y_test.mean()))


# ---------------------------------------------------------------------------
def test_predict_round_trip():
    print("\n[3] predict.py loads bundle and produces a probability")
    # Train a real-but-tiny model so we have a bundle on disk.
    df = add_rolling_features(generate(n_people=40, n_days=80, seed=2))
    train, val, _ = time_split(df)
    X_train = train[FEATURE_COLS].values.astype(float)
    y_train = train["burnout"].values.astype(int)
    X_val   = val[FEATURE_COLS].values.astype(float)
    y_val   = val["burnout"].values.astype(int)
    (Xtr_s, _Xv_s), (mu, sigma) = standardize(X_train, X_val)

    lr = LogisticRegression(n_iter=400).fit(Xtr_s, y_train)
    gbt = GradientBoostedClassifier(n_estimators=20, max_depth=2, seed=0)
    gbt.fit(X_train, y_train, X_val=X_val, y_val=y_val)
    platt = PlattScaling().fit(gbt.predict_proba(X_val), y_val)
    iso = IsotonicRegression().fit(gbt.predict_proba(X_val), y_val)

    bundle = {
        "feature_cols": FEATURE_COLS,
        "standardization": {"mu": mu.tolist(), "sigma": sigma.tolist()},
        "logreg": lr.to_dict(),
        "gbt": gbt.to_dict(),
        "platt": platt.to_dict(),
        "isotonic": iso.to_dict(),
        "metrics": {},
    }

    # Save to a temp file and point predict.py at it via monkey-patching.
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "model_bundle.json"
        bundle_path.write_text(json.dumps(bundle))

        import predict as _predict
        original = _predict.BUNDLE
        _predict.BUNDLE = bundle_path
        try:
            for case in ("ok", "bad"):
                raw = _predict.DEMOS[case]
                hist = [{**raw, "events": ""} for _ in range(28)]
                scores = _predict.score_team(raw, history=hist, recent_events=[])
                check(f"predict {case}: ensemble in [0,1]",
                      0 <= scores["ensemble_mean"] <= 1,
                      f"got {scores['ensemble_mean']}")
                check(f"predict {case}: gbt_calibrated key present",
                      "gbt_calibrated" in scores)
            # Sanity: 'bad' case should outscore 'ok' case
            ok_p = _predict.score_team(_predict.DEMOS["ok"],
                history=[{**_predict.DEMOS["ok"], "events": ""}] * 28)
            bad_p = _predict.score_team(_predict.DEMOS["bad"],
                history=[{**_predict.DEMOS["bad"], "events": ""}] * 28)
            check("'bad' case > 'ok' case (ensemble)",
                  bad_p["ensemble_mean"] > ok_p["ensemble_mean"],
                  f"ok={ok_p['ensemble_mean']:.3f}  bad={bad_p['ensemble_mean']:.3f}")
        finally:
            _predict.BUNDLE = original


# ---------------------------------------------------------------------------
def test_load_real_round_trip():
    print("\n[4] CSV round-trip through load_real (daily)")
    import load_real
    rows = []
    for day_idx in range(30):
        rows.append({
            "person_id": "alice@co",
            "team_id": "alice@co",
            "date": (pd.Timestamp("2026-01-05") + pd.Timedelta(days=day_idx)).isoformat(),
            "submitted_at": "2026-01-05T10:00:00",
            "hours": 8 + (day_idx % 4) * 0.5,
            "sleep": 7.0 - 0.05 * day_idx,
            "mood": 6, "stress": 4 + 0.1 * day_idx,
            "mgr_support": 7, "peer_support": 7,
            "deadline_pressure": 4 + 0.1 * day_idx, "on_call_load": 0.0,
            "events": "" if day_idx != 15 else "deadline_crunch",
            "burnout": 0 if day_idx < 25 else 1,
        })
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "checkins.csv"
        pd.DataFrame(rows).to_csv(p, index=False)
        df = load_real.from_csv(p)
        check("loaded row count matches", len(df) == 30, f"got {len(df)}")
        check("day index is 0..N-1", list(df["day"]) == list(range(30)))
        check("events parsed", df.loc[15, "events"] == "deadline_crunch")
        check("burnout column preserved", df["burnout"].sum() == 5)


# ---------------------------------------------------------------------------
def test_event_types_consistency():
    print("\n[5] Schema consistency checks")
    check("EVENT_TYPES non-empty", len(EVENT_TYPES) > 0)
    check("RAW_COLS subset of FEATURE_COLS",
          all(c in FEATURE_COLS for c in RAW_COLS))
    # Counts: 8 raw + 16 ma (ma7+ma28) + 5 delta + 4 std + 2 slope + 3 had_*_14d + 3 misc = 41
    expected = (len(RAW_COLS)
                + 2 * len(RAW_COLS)              # ma7 + ma28
                + 5 + 4 + 2                       # delta + std + slope
                + 3                               # had_*_14d
                + 3)                              # days_since_pto + 2 interactions
    check(f"FEATURE_COLS has expected length {expected}",
          len(FEATURE_COLS) == expected,
          f"got {len(FEATURE_COLS)}")


# ---------------------------------------------------------------------------
def test_train_real_blend():
    """Real-data path: write a small synthetic checkins.csv, then run
    train_real.py through its --blend mode (since 8 rows alone won't
    pass the min-rows guard). Confirms load_real -> add_rolling_features
    -> models pipeline end-to-end on the real-data API."""
    print("\n[6] train_real --blend smoke test (daily)")
    import subprocess, sys as _sys

    # Build a tiny realistic daily checkins.csv (30 days, escalating stress).
    rows = []
    for day_idx in range(30):
        rows.append({
            "person_id": "alice@co", "team_id": "alice@co",
            "date": (pd.Timestamp("2026-01-05")
                     + pd.Timedelta(days=day_idx)).date().isoformat(),
            "submitted_at": "2026-01-05T10:00:00",
            "hours": 8 + (day_idx % 5) * 0.5,
            "sleep": 7.2 - 0.03 * day_idx,
            "mood": 7 - 0.05 * day_idx,
            "stress": 4 + 0.1 * day_idx,
            "mgr_support": 7, "peer_support": 7,
            "deadline_pressure": 4 + 0.08 * day_idx, "on_call_load": 0.0,
            "events": "" if day_idx != 18 else "deadline_crunch",
            "burnout": 0 if day_idx < 22 else 1,
        })

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "checkins.csv"
        pd.DataFrame(rows).to_csv(csv_path, index=False)

        # Invoke as a subprocess so we get a clean import of train_real.
        result = subprocess.run(
            [_sys.executable, str(OUT / "train_real.py"),
             "--csv", str(csv_path),
             "--blend", "20",
             "--min-rows", "5", "--min-positives", "1"],
            capture_output=True, text=True, cwd=str(OUT),
        )
        ok = result.returncode == 0
        if not ok:
            print("    --- stdout ---")
            print(result.stdout[-800:])
            print("    --- stderr ---")
            print(result.stderr[-800:])
        check("train_real --blend exited cleanly", ok)
        check("train_real wrote model_bundle_real.json",
              (OUT / "model_bundle_real.json").exists())
        check("train_real wrote metrics_real.json",
              (OUT / "metrics_real.json").exists())
        # Clean up the test artifacts so a real run isn't fooled.
        for f in ("model_bundle_real.json", "metrics_real.json"):
            (OUT / f).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 60)
    print("  Burnout pipeline smoke test")
    print("=" * 60)

    test_generation_and_features()
    test_models_fit_and_predict()
    test_predict_round_trip()
    test_load_real_round_trip()
    test_event_types_consistency()
    test_train_real_blend()

    print()
    print("=" * 60)
    print(f"  {PASSED} passed, {FAILED} failed")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
