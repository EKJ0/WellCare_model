"""Interactive burnout-risk tracker.

Usage:
    python predict.py                # interactive prompt (default)
    python predict.py --demo bad     # canned stressed case
    python predict.py --demo ok      # canned healthy case
    python predict.py --json '{...}' # one-shot scoring from a raw-signals JSON

You can also import score_team(raw, history=None) to use programmatically."""

from __future__ import annotations
import argparse
import datetime as _dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scenarios import RAW_COLS, FEATURE_COLS, EVENT_TYPES, add_rolling_features

OUT = Path(__file__).resolve().parent
BUNDLE = OUT / "model_bundle.json"
LAST   = OUT / "last_prediction.json"   # most recent score (overwritten)
LOG    = OUT / "predictions_log.csv"    # append-only history of every score


# --- Reconstruct the trained models from the JSON bundle -------------------
def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def _walk_tree(node: dict, x: np.ndarray) -> float:
    while not node["l"]:
        node = node["L"] if x[node["f"]] <= node["t"] else node["R"]
    return node["v"]


def _gbt_predict(gbt: dict, X: np.ndarray) -> np.ndarray:
    F = np.full(len(X), gbt["init_log_odds"])
    for tree in gbt["trees"]:
        F = F + gbt["learning_rate"] * np.array([_walk_tree(tree, x) for x in X])
    return _sigmoid(F)


def _logreg_predict(lr: dict, X: np.ndarray) -> np.ndarray:
    w = np.array(lr["weights"]); b = float(lr["bias"])
    return _sigmoid(X @ w + b)


def _platt_apply(platt: dict, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    s = np.log(p / (1 - p))
    return _sigmoid(platt["a"] * s + platt["b"])


# --- Build the feature row from raw signals + history ---------------------
# We construct a tiny single-team dataframe of (history + current week) and
# run the *same* add_rolling_features() the trainer used. Single source of
# truth means train and predict can never disagree on feature definitions.
def _build_features(raw: dict,
                    history: list[dict] | None = None,
                    recent_events: list[str] | None = None) -> np.ndarray:
    """Build today's feature row.

    `history` is a list of past *daily* check-ins (oldest -> newest). It
    only needs to cover the longest rolling window the model uses
    (28 days). Passing fewer days is fine — the rolling means will just
    use whatever is available."""
    history = history or []
    rows = []
    for i, h in enumerate(history):
        rows.append({"person_id": 0, "day": i,
                     **{c: float(h[c]) for c in RAW_COLS},
                     "events": h.get("events", "")})
    rows.append({"person_id": 0, "day": len(history),
                 **{c: float(raw[c]) for c in RAW_COLS},
                 "events": "|".join(recent_events or [])})

    df = add_rolling_features(pd.DataFrame(rows))
    feats = df.iloc[-1][FEATURE_COLS].values.astype(float)
    assert len(feats) == len(FEATURE_COLS), \
        f"feature count mismatch: built {len(feats)}, expected {len(FEATURE_COLS)}"
    return feats


def score_team(raw: dict, history: list[dict] | None = None,
               recent_events: list[str] | None = None) -> dict:
    bundle = json.loads(BUNDLE.read_text())
    feats = _build_features(raw, history, recent_events)
    mu    = np.array(bundle["standardization"]["mu"])
    sigma = np.array(bundle["standardization"]["sigma"])
    feats_std = (feats - mu) / sigma

    p_lr      = float(_logreg_predict(bundle["logreg"], feats_std[None, :])[0])
    p_gbt_raw = float(_gbt_predict(bundle["gbt"], feats[None, :])[0])

    out = {"logreg": p_lr, "gbt_raw": p_gbt_raw}

    # Calibrated GBT — prefer Platt if the bundle has it (new train.py),
    # fall back to isotonic for older bundles.
    if "platt" in bundle:
        p_cal = float(_platt_apply(bundle["platt"], np.array([p_gbt_raw]))[0])
        out["gbt_calibrated"] = p_cal
    elif "isotonic" in bundle:
        iso = bundle["isotonic"]
        x_t = np.array(iso["x"]); y_v = np.array(iso["y"])
        idx = int(np.clip(np.searchsorted(x_t, p_gbt_raw, side="left"),
                          0, len(y_v) - 1))
        out["gbt_calibrated"] = float(y_v[idx])
    else:
        out["gbt_calibrated"] = p_gbt_raw

    out["ensemble_mean"] = float((p_lr + out["gbt_calibrated"]) / 2)
    return out


# --- Pretty output ---------------------------------------------------------
def _bar(p: float, width: int = 30) -> str:
    n = max(0, min(width, int(round(p * width))))
    return "[" + "#" * n + "." * (width - n) + "]"


def _verdict(p: float, base_rate: float = 0.12) -> str:
    if p < base_rate * 0.5:    return "LOW       (well below typical)"
    if p < base_rate * 1.5:    return "TYPICAL   (around the base rate)"
    if p < base_rate * 3.0:    return "ELEVATED  (2-3x base rate)"
    if p < base_rate * 5.0:    return "HIGH      (3-5x base rate)"
    return "SEVERE    (5x+ base rate)"


def _print_scores(raw: dict, scores: dict, events: list[str] | None = None) -> None:
    print("\n  Inputs:")
    for k in RAW_COLS:
        print(f"    {k:<20} {raw[k]:>6.2f}")
    if events:
        print(f"    {'recent_events':<20} {', '.join(events)}")
    print("\n  Predicted burnout risk (next-week probability):")
    for label, key in [("Logistic regression", "logreg"),
                       ("GBT (calibrated)",    "gbt_calibrated"),
                       ("Ensemble mean",       "ensemble_mean")]:
        p = scores[key]
        print(f"    {label:<22} {p:5.1%}  {_bar(p)}")
    print(f"\n  Verdict (ensemble): {_verdict(scores['ensemble_mean'])}")
    print(f"\n  >>> YOUR BURNOUT RISK: {scores['ensemble_mean']:.1%} <<<")


def _save_prediction(raw: dict, scores: dict,
                     label: str | None = None,
                     events: list[str] | None = None) -> None:
    """Persist the most recent score to disk so the user can find it later.

    `last_prediction.json` is overwritten each time; `predictions_log.csv`
    is appended so they can plot trends over time."""
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    events = events or []
    record = {
        "timestamp": ts,
        "label": label or "",
        "inputs": raw,
        "recent_events": events,
        "burnout_risk_percent": round(scores["ensemble_mean"] * 100, 2),
        "verdict": _verdict(scores["ensemble_mean"]).split()[0],
        "scores": {k: round(v, 4) for k, v in scores.items()},
    }
    LAST.write_text(json.dumps(record, indent=2))

    new_log = not LOG.exists()
    cols = (["timestamp", "label", "burnout_risk_percent", "verdict"]
            + list(RAW_COLS)
            + ["recent_events", "logreg", "gbt_raw", "gbt_calibrated"])
    row = {
        "timestamp": ts, "label": record["label"],
        "burnout_risk_percent": record["burnout_risk_percent"],
        "verdict": record["verdict"],
        **raw,
        "recent_events":  "|".join(events),
        "logreg":         round(scores["logreg"], 4),
        "gbt_raw":        round(scores["gbt_raw"], 4),
        "gbt_calibrated": round(scores["gbt_calibrated"], 4),
    }
    with LOG.open("a", encoding="utf-8") as f:
        if new_log:
            f.write(",".join(cols) + "\n")
        f.write(",".join(str(row[c]) for c in cols) + "\n")
    print(f"  Saved to: {LAST.name}  (and appended to {LOG.name})")


# --- Interactive REPL ------------------------------------------------------
# (lo, hi, default, label) per raw signal. Defaults are the population
# baselines from scenarios.py so an empty press-enter run scores ~base rate.
SIGNAL_SPEC: list[tuple[str, float, float, float, str]] = [
    ("hours",              0, 16,  8.0, "Hours worked today"),
    ("sleep",              3, 11,  7.0, "Hours slept last night"),
    ("mood",               1, 10,  7.0, "Self-reported mood right now (1=worst, 10=best)"),
    ("stress",             1, 10,  4.5, "Stress level today (1=none, 10=max)"),
    ("mgr_support",        1, 10,  7.0, "Manager support today (1-10)"),
    ("peer_support",       1, 10,  7.0, "Peer support today (1-10)"),
    ("deadline_pressure",  1, 10,  4.0, "Today's workload pressure (1-10)"),
    ("on_call_load",       0, 1.5, 0.2, "On-call load today (0=no, 0.6=a bit, 1.2=heavy)"),
]


def _ask(name: str, lo: float, hi: float, default: float, label: str) -> float:
    while True:
        s = input(f"  {label}\n    {name} [{lo}-{hi}, default {default}]: ").strip()
        if not s:
            return float(default)
        try:
            v = float(s)
        except ValueError:
            print("    !! not a number, try again")
            continue
        if v < lo or v > hi:
            print(f"    !! must be in [{lo}, {hi}]")
            continue
        return v


def _prompt_raw(prefill: dict | None = None) -> dict:
    print("\nEnter today's signals (press Enter for default):")
    raw = {}
    for name, lo, hi, default, label in SIGNAL_SPEC:
        d = prefill[name] if prefill else default
        raw[name] = _ask(name, lo, hi, d, label)
    return raw


# Only the events the model actually has features for. Other event types
# affect the prediction only via the raw signals you already typed in.
PROMPTABLE_EVENTS = ["layoff", "reorg", "deadline_crunch", "pto"]


def _prompt_events(prefill: list[str] | None = None) -> list[str]:
    default = ",".join(prefill) if prefill else ""
    s = input(
        f"\n  Anything notable in the last couple of weeks?\n"
        f"    options: {', '.join(PROMPTABLE_EVENTS)}\n"
        f"    (comma-separated, Enter for '{default or 'none'}'): "
    ).strip()
    if not s:
        return list(prefill or [])
    chosen = [t.strip() for t in s.split(",") if t.strip()]
    bad = [c for c in chosen if c not in EVENT_TYPES]
    if bad:
        print(f"    !! ignoring unknown events: {bad}")
        chosen = [c for c in chosen if c in EVENT_TYPES]
    return chosen


def interactive() -> None:
    if not BUNDLE.exists():
        print(f"!! No model bundle at {BUNDLE}.")
        print("!! Run `python train.py` first to train and save the model.")
        return

    print("=" * 60)
    print("  WellCare Daily Risk Tracker  -  interactive mode")
    print("=" * 60)
    print("Tip: hit Enter at any prompt to accept the default.\n"
          "     History defaults to a flat 28-day window matching today,\n"
          "     so single-day scoring assumes you have been at this\n"
          "     level for a while (worst case for the rolling means).")

    raw, events = None, None
    while True:
        raw = _prompt_raw(prefill=raw)
        events = _prompt_events(prefill=events)
        # Build a 28-day flat history; tag the events on the most recent
        # day so rolling event-recency features pick them up.
        history = [{**raw, "events": ""} for _ in range(27)]
        history.append({**raw, "events": "|".join(events)})
        scores = score_team(raw, history=history, recent_events=events)
        _print_scores(raw, scores, events=events)
        label = input("\n  Optional label for this score (e.g. 'me-this-week'): ").strip()
        _save_prediction(raw, scores, label=label, events=events)

        print("\nNext: [r]e-score with tweaks, [n]ew team, [q]uit")
        choice = (input("> ").strip().lower() or "q")[0]
        if choice == "q":
            break
        if choice == "n":
            raw, events = None, None
        # 'r' falls through and reuses `raw` + `events` as the prefill


# --- Demo cases (one-day snapshots) ----------------------------------------
DEMOS = {
    "ok": {
        "hours": 7.5, "sleep": 7.8, "mood": 8, "stress": 3,
        "mgr_support": 8, "peer_support": 8,
        "deadline_pressure": 3, "on_call_load": 0.0,
    },
    "bad": {
        "hours": 12.5, "sleep": 5.0, "mood": 4, "stress": 8,
        "mgr_support": 4, "peer_support": 5,
        "deadline_pressure": 8, "on_call_load": 0.6,
    },
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--demo", choices=list(DEMOS), help="score a canned case")
    ap.add_argument("--json", help='one-shot scoring from raw-signals JSON, e.g. \'{"hours":55,...}\'')
    ap.add_argument("--events", default="",
                    help="comma-separated recent events, e.g. layoff,deadline_crunch")
    ap.add_argument("--label", default="", help="tag this score in the saved log")
    args = ap.parse_args()

    if args.demo or args.json:
        raw = DEMOS[args.demo] if args.demo else json.loads(args.json)
        for k in [c for c, *_ in SIGNAL_SPEC]:
            if k not in raw:
                raise SystemExit(f"missing required signal '{k}' in input")
        events = [e.strip() for e in args.events.split(",") if e.strip()]
        history = [{**raw, "events": ""} for _ in range(27)]
        history.append({**raw, "events": "|".join(events)})
        scores = score_team(raw, history=history, recent_events=events)
        _print_scores(raw, scores, events=events)
        _save_prediction(raw, scores,
                         label=args.label or args.demo or "json",
                         events=events)
        return

    interactive()


if __name__ == "__main__":
    main()
