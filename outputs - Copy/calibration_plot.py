"""Reliability diagram: does '30%' actually happen 30% of the time?

A perfectly calibrated model lies on the diagonal — when it says
'30% probability of burnout', the empirical rate among those
predictions is also 30%. Real models drift, and the shape of the
drift tells you what kind of correction you need.

Outputs:
  - ASCII reliability diagram printed to stdout (no deps).
  - calibration.svg with the same plot, openable in any browser.
  - calibration.json with bin counts + Brier decomposition (the bias /
    variance / refinement split) so you can track drift over time.

Usage:
    python calibration_plot.py
    python calibration_plot.py --score risk_logreg
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
SCORED = OUT / "scored_teams.csv"
SCORE_COL_PREFERENCE = ("risk_platt", "risk_isotonic", "risk_logreg", "risk_raw_gbt")
N_BINS = 10


# --- Brier score decomposition ---------------------------------------------
# Murphy's decomposition: Brier = reliability - resolution + uncertainty.
#   reliability ↓ = empirical rate matches predicted rate (calibration)
#   resolution  ↑ = bin means are spread apart (model is informative)
#   uncertainty   = base-rate variance (irreducible)
def brier_decomposition(p, y, n_bins=10):
    edges = np.linspace(0, 1, n_bins + 1)
    base_rate = float(y.mean())
    rel = res = 0.0
    for i in range(n_bins):
        mask = (p >= edges[i]) & (p < edges[i + 1])
        if i == n_bins - 1:
            mask |= (p == edges[-1])
        n_k = int(mask.sum())
        if n_k == 0:
            continue
        p_bar_k = float(p[mask].mean())
        y_bar_k = float(y[mask].mean())
        rel += n_k * (p_bar_k - y_bar_k) ** 2
        res += n_k * (y_bar_k - base_rate) ** 2
    rel /= len(y); res /= len(y)
    unc = base_rate * (1 - base_rate)
    return rel, res, unc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", default=None,
                    help="risk column to evaluate (default: best available)")
    ap.add_argument("--bins", type=int, default=N_BINS)
    args = ap.parse_args()

    if not SCORED.exists():
        raise SystemExit(f"{SCORED.name} missing. Run train.py first.")
    df = pd.read_csv(SCORED)

    score_col = args.score or next(
        (c for c in SCORE_COL_PREFERENCE if c in df.columns), None)
    if score_col not in df.columns:
        raise SystemExit(f"score column '{score_col}' not in scored_teams.csv")

    p = df[score_col].values.astype(float)
    y = df["burnout"].values.astype(int)

    # --- Bin into deciles by predicted probability ------------------------
    edges = np.linspace(0, 1, args.bins + 1)
    bin_idx = np.minimum(np.searchsorted(edges, p, side="right") - 1,
                         args.bins - 1)
    bins = []
    for i in range(args.bins):
        mask = bin_idx == i
        bins.append({
            "bin":            i + 1,
            "lo":             float(edges[i]),
            "hi":             float(edges[i + 1]),
            "count":          int(mask.sum()),
            "mean_pred":      float(p[mask].mean()) if mask.any() else None,
            "empirical_rate": float(y[mask].mean()) if mask.any() else None,
        })

    # --- ASCII diagram ----------------------------------------------------
    print("=" * 76)
    print(f"  Reliability diagram  (using {score_col}, {args.bins} bins)")
    print("=" * 76)
    print(f"  Diagonal '|' = perfect calibration. 'P' = predicted, 'E' = empirical.")
    print()
    width = 40
    print(f"  {'bin':<6} {'count':<6} {'pred':<6} {'empir':<6} "
          f"  {'0%':<3}{'':<{width - 6}}{'100%':>5}")
    print("  " + "-" * (24 + width + 3))
    for b in bins:
        if b["count"] == 0:
            print(f"  {b['bin']:<6} {b['count']:<6} {'-':<6} {'-':<6}")
            continue
        # Build a row showing the bin's expected position (P) and actual (E)
        row = ["."] * width
        # Mark the diagonal at this bin's expected midpoint
        mid = (b["lo"] + b["hi"]) / 2
        diag_pos = min(width - 1, int(round(mid * width)))
        row[diag_pos] = "|"
        p_pos = min(width - 1, int(round(b["mean_pred"] * width)))
        e_pos = min(width - 1, int(round(b["empirical_rate"] * width)))
        # Place markers (E may overwrite P or |, that's fine)
        row[p_pos] = "P"
        row[e_pos] = "E" if e_pos != p_pos else "*"  # * = perfectly aligned
        bar = "".join(row)
        print(f"  {b['bin']:<6} {b['count']:<6} {b['mean_pred']:<6.2f} "
              f"{b['empirical_rate']:<6.2f}   [{bar}]")

    # --- Brier decomposition ----------------------------------------------
    rel, res, unc = brier_decomposition(p, y, args.bins)
    brier = rel - res + unc
    print()
    print("Brier decomposition (Murphy):")
    print(f"  reliability  {rel:.4f}   <- low = well calibrated")
    print(f"  resolution   {res:.4f}   <- high = model is informative")
    print(f"  uncertainty  {unc:.4f}   <- irreducible (base-rate variance)")
    print(f"  total Brier  {brier:.4f}  (= rel - res + unc)")

    # Quick interpretation
    print()
    print("Interpretation:")
    if rel < 0.005:
        print("  Calibration is excellent. No correction needed.")
    elif rel < 0.015:
        print("  Calibration is acceptable. A light Platt re-fit might tighten it.")
    else:
        print("  Calibration is weak. Re-fit Platt or isotonic on a fresher val set.")

    # Find systematic biases
    overconfident = [b for b in bins if b["count"] >= 10
                     and b["mean_pred"] - b["empirical_rate"] > 0.10]
    underconfident = [b for b in bins if b["count"] >= 10
                      and b["empirical_rate"] - b["mean_pred"] > 0.10]
    if overconfident:
        bs = ",".join(str(b["bin"]) for b in overconfident)
        print(f"  Overconfident in bins {bs} (predicting too high).")
    if underconfident:
        bs = ",".join(str(b["bin"]) for b in underconfident)
        print(f"  Underconfident in bins {bs} (predicting too low).")

    # --- SVG --------------------------------------------------------------
    svg = render_svg(bins, score_col)
    (OUT / "calibration.svg").write_text(svg)
    (OUT / "calibration.json").write_text(json.dumps({
        "score_col": score_col,
        "n_bins": args.bins,
        "bins": bins,
        "brier_total": brier,
        "brier_reliability": rel,
        "brier_resolution": res,
        "brier_uncertainty": unc,
    }, indent=2))
    print()
    print("Wrote: calibration.svg, calibration.json")


def render_svg(bins, label, size=400, pad=40):
    W = H = size
    inner = size - 2 * pad
    # Diagonal
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" style="font-family: -apple-system, sans-serif; font-size: 11px;">',
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="white"/>',
        # axes
        f'<line x1="{pad}" y1="{H - pad}" x2="{W - pad}" y2="{H - pad}" stroke="#999" />',
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{H - pad}" stroke="#999" />',
        # diagonal
        f'<line x1="{pad}" y1="{H - pad}" x2="{W - pad}" y2="{pad}" '
        f'stroke="#bbb" stroke-dasharray="4 3"/>',
        # labels
        f'<text x="{W / 2}" y="{H - 8}" text-anchor="middle">predicted probability</text>',
        f'<text x="14" y="{H / 2}" text-anchor="middle" '
        f'transform="rotate(-90 14 {H / 2})">empirical rate</text>',
        f'<text x="{W / 2}" y="20" text-anchor="middle" '
        f'font-weight="600">Reliability — {label}</text>',
    ]
    pts = []
    for b in bins:
        if b["count"] == 0:
            continue
        x = pad + b["mean_pred"] * inner
        y = (H - pad) - b["empirical_rate"] * inner
        r = max(2.5, 2.5 + 0.04 * b["count"])
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" '
            f'fill="#3F6B3A" fill-opacity="0.6" stroke="#2F5A2A" />')
        pts.append((x, y))
    if len(pts) > 1:
        path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.append(f'<path d="{path}" fill="none" stroke="#3F6B3A" '
                     f'stroke-width="1.5" />')
    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    main()
