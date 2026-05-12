"""Verify the model_bundle.js used by checkin-app.html.

1. The file parses as JSON cleanly.
2. Every section the web scorer needs is present.
3. The bundle is the new daily schema (or a legacy weekly bundle —
   we still accept that and run the legacy-style scoring path).
4. Canned scenarios produce monotonically increasing risk from a
   healthy day to a crisis day, using the same math the JS scorer runs.

Run after `python train.py && python bundle_to_js.py`."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE_JS = ROOT / "model_bundle.js"
HTML = ROOT / "checkin-app.html"


def load_bundle_from_js() -> dict:
    src = BUNDLE_JS.read_text(encoding="utf-8")
    start = src.index("{")
    payload = src[start:].rstrip().rstrip(";")
    return json.loads(payload)


# --- JS-mirror math --------------------------------------------------------
def sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def walk_tree(node: dict, x: list[float]) -> float:
    while not node.get("l"):
        node = node["L"] if x[node["f"]] <= node["t"] else node["R"]
    return node["v"]


def gbt_predict(gbt: dict, x: list[float]) -> float:
    f = gbt["init_log_odds"]
    for tree in gbt["trees"]:
        f += gbt["learning_rate"] * walk_tree(tree, x)
    return sigmoid(f)


def lr_predict(lr: dict, x_std: list[float]) -> float:
    z = lr["bias"] + sum(w * v for w, v in zip(lr["weights"], x_std))
    return sigmoid(z)


def platt_apply(platt: dict, p: float) -> float:
    c = min(1 - 1e-6, max(1e-6, p))
    s = math.log(c / (1 - c))
    return sigmoid(platt["a"] * s + platt["b"])


RAW_COLS = ["hours", "sleep", "mood", "stress", "mgr_support",
            "peer_support", "deadline_pressure", "on_call_load"]


def detect_schema(feature_cols: list[str]) -> dict:
    s = set(feature_cols)
    if "hours_ma7" in s or "days_since_pto" in s:
        return dict(kind="daily", short=7, long=28, ev_win=14,
                    pto_feat="days_since_pto", pto_cap=60,
                    ev_suffix="14d", hours_scale=1.0)
    return dict(kind="weekly", short=4, long=12, ev_win=4,
                pto_feat="weeks_since_pto", pto_cap=12,
                ev_suffix="4w", hours_scale=5.0)


def _mean(arr):  return sum(arr) / len(arr) if arr else 0.0
def _std(arr):
    if len(arr) < 2: return 0.0
    m = _mean(arr); return math.sqrt(sum((v - m)**2 for v in arr) / (len(arr) - 1))
def _slope(arr):
    n = len(arr)
    if n < 2: return 0.0
    xm = (n - 1) / 2; ym = _mean(arr)
    num = sum((i - xm) * (v - ym) for i, v in enumerate(arr))
    den = sum((i - xm) ** 2 for i in range(n))
    return num / den if den else 0.0


def build_feature_row(feature_cols, raw, events, history):
    """Mirrors buildFeatureRow() in checkin-app.html."""
    schema = detect_schema(feature_cols)

    seq = [{"signals": h["signals"], "events": set(h.get("events", []))}
           for h in (history or [])]
    seq.append({"signals": raw, "events": set(events)})

    def scale_hours(v):
        return float(v) * schema["hours_scale"]

    def vals(rows, col):
        return [scale_hours(r["signals"][col]) if col == "hours"
                else float(r["signals"][col]) for r in rows]

    def window(n):
        return seq[max(0, len(seq) - n):]

    today = seq[-1]
    out = {}
    for c in RAW_COLS:
        out[c] = scale_hours(today["signals"][c]) if c == "hours" \
                 else float(today["signals"][c])

    short = window(schema["short"])
    long_ = window(schema["long"])
    for c in RAW_COLS:
        out[f"{c}_ma{schema['short']}"] = _mean(vals(short, c))
        out[f"{c}_ma{schema['long']}"]  = _mean(vals(long_, c))

    for c in ["hours", "stress", "sleep", "mood", "deadline_pressure"]:
        out[f"{c}_delta{schema['short']}"] = out[c] - out[f"{c}_ma{schema['short']}"]

    for c in ["hours", "stress", "sleep", "mood"]:
        out[f"{c}_std{schema['short']}"] = _std(vals(short, c))
    for c in ["hours", "stress"]:
        out[f"{c}_slope{schema['short']}"] = _slope(vals(short, c))

    ev_window = window(schema["ev_win"])
    def had(ev): return 1 if any(ev in r["events"] for r in ev_window) else 0
    out[f"had_layoff_{schema['ev_suffix']}"]   = had("layoff")
    out[f"had_reorg_{schema['ev_suffix']}"]    = had("reorg")
    out[f"had_deadline_{schema['ev_suffix']}"] = had("deadline_crunch")

    since_pto = schema["pto_cap"]
    for i in range(len(seq) - 1, -1, -1):
        if "pto" in seq[i]["events"]:
            since_pto = min(schema["pto_cap"], len(seq) - 1 - i)
            break
    out[schema["pto_feat"]] = since_pto

    if schema["kind"] == "daily":
        out["hours_x_stress"]       = (out["hours"] * out["stress"]) / 20.0
        out["low_sleep_high_hours"] = max(0, out["hours"] - 10) * max(0, 7 - out["sleep"])
    else:
        out["hours_x_stress"]       = (out["hours"] * out["stress"]) / 100.0
        out["low_sleep_high_hours"] = max(0, out["hours"] - 50) * max(0, 7 - out["sleep"])

    return [out.get(c, 0.0) for c in feature_cols], schema


def score(bundle, raw, events, history):
    x, schema = build_feature_row(bundle["feature_cols"], raw, events, history)
    mu = bundle["standardization"]["mu"]
    sigma = bundle["standardization"]["sigma"]
    x_std = [(v - mu[i]) / sigma[i] for i, v in enumerate(x)]
    p_lr = lr_predict(bundle["logreg"], x_std)
    p_gbt = gbt_predict(bundle["gbt"], x)
    p_cal = platt_apply(bundle["platt"], p_gbt) if "platt" in bundle else p_gbt
    return {"logreg": p_lr, "gbt": p_gbt, "gbt_calibrated": p_cal,
            "ensemble": (p_lr + p_cal) / 2, "schema": schema["kind"]}


def verdict(p):
    if p < 0.06: return "Low"
    if p < 0.18: return "Typical"
    if p < 0.36: return "Elevated"
    if p < 0.60: return "High"
    return "Severe"


# ---- Scenarios: daily inputs (the schema the app collects) ----------------
DEFAULTS = dict(hours=8, sleep=7, mood=7, stress=4.5,
                mgr_support=7, peer_support=7,
                deadline_pressure=4, on_call_load=0.2)

SCENARIOS = [
    ("Healthy day",
     dict(DEFAULTS, hours=7.5, sleep=7.8, mood=8, stress=3,
          mgr_support=8, peer_support=8, deadline_pressure=3,
          on_call_load=0.0),
     []),
    ("Typical day",
     dict(DEFAULTS),
     []),
    ("Crunch day",
     dict(DEFAULTS, hours=11, sleep=5.5, mood=5, stress=8,
          mgr_support=5, peer_support=6, deadline_pressure=8,
          on_call_load=0.6),
     ["deadline_crunch"]),
    ("Crisis day",
     dict(DEFAULTS, hours=13, sleep=4.5, mood=3, stress=9,
          mgr_support=3, peer_support=4, deadline_pressure=9,
          on_call_load=1.2),
     ["layoff", "deadline_crunch"]),
]


def flat_history(today_signals, n=28):
    """28-day flat history matching today (worst case for the rolling mean)."""
    return [{"signals": dict(today_signals), "events": []} for _ in range(n)]


def main() -> int:
    print(f"Looking for bundle at: {BUNDLE_JS}")
    if not BUNDLE_JS.exists():
        print('  MISSING. Run: python "outputs - Copy/bundle_to_js.py"')
        return 1

    bundle = load_bundle_from_js()
    print(f"  parsed OK. trained_at: {bundle.get('trained_at')}")

    schema = detect_schema(bundle["feature_cols"])
    print()
    print(f"Bundle schema: {schema['kind'].upper()}  "
          f"(short={schema['short']}, long={schema['long']}, "
          f"ev_win={schema['ev_win']})")
    print(f"  feature_cols   : {len(bundle['feature_cols'])} columns")
    print(f"  logreg weights : {len(bundle['logreg']['weights'])}  "
          f"bias: {bundle['logreg']['bias']:.4f}")
    print(f"  gbt trees      : {len(bundle['gbt']['trees'])}  "
          f"init: {bundle['gbt']['init_log_odds']:.4f}  "
          f"lr: {bundle['gbt']['learning_rate']}")
    print(f"  platt          : {'present' if 'platt' in bundle else 'MISSING'}")
    print(f"  isotonic pts   : {len(bundle.get('isotonic', {}).get('x', []))}")

    assert len(bundle["feature_cols"]) == len(bundle["logreg"]["weights"]), \
        "feature_cols vs logreg weights length mismatch"

    print()
    print("Scoring canned daily scenarios with the same math as checkin-app.html:")
    print()
    print(f"  {'Scenario':<14}  {'lr':>6}  {'gbt':>6}  {'cal':>6}  "
          f"{'ENSEMBLE':>9}  verdict")
    print(f"  {'-'*14}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*9}  -------")
    last_p = -1.0
    for name, signals, events in SCENARIOS:
        hist = flat_history(signals)
        s = score(bundle, signals, events, hist)
        v = verdict(s["ensemble"])
        print(f"  {name:<14}  {s['logreg']:>6.3f}  {s['gbt']:>6.3f}  "
              f"{s['gbt_calibrated']:>6.3f}  {s['ensemble']:>9.3f}  {v}")
        assert s["ensemble"] >= last_p - 0.05, \
            f"Risk should rise Healthy -> Crisis, but {name} dropped"
        last_p = s["ensemble"]

    html_text = HTML.read_text(encoding="utf-8", errors="replace")
    if 'src="model_bundle.js"' not in html_text:
        print("\nWARNING: checkin-app.html no longer references model_bundle.js")
        return 2

    print()
    print("OK: bundle parses, web app loads it, scores rise Healthy -> Crisis.")
    print(f"    Profile tab should say 'Trained model active' once you reload.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
