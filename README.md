# Burnout-Risk Model

A small, end-to-end burnout-risk prediction system you can run on your
laptop. Models a team-week as 8 self-report signals + a few event flags,
predicts a `Bernoulli(burnout)` probability, and ships a friendly
check-in app for collecting real data.

Everything is from-scratch numpy + a single-file React app. No sklearn,
no torch, no backend. The whole thing trains in ~1 minute and the web
app installs as a PWA on your phone.

---

## Quick start

```powershell
# 1. install
pip install -r requirements.txt

# 2. train on synthetic data (~1-2 min)
cd "outputs - Copy"
python train.py

# 3. score interactively
python predict.py            # CLI form
#   or open ../checkin-app.html in a browser
```

That's it. Steps 2 and 3 are independent of any data collection.

---

## What's where

```
WellCare_model/
├── requirements.txt              # numpy, pandas
├── README.md                     # this file
├── checkin-app.html              # standalone PWA — open in any browser
├── manifest.webmanifest          # PWA install metadata
├── sw.js                         # offline service worker
└── outputs - Copy/               # the Python ML pipeline
    │
    ├── scenarios.py              # synthetic data generator + feature engineering
    ├── models.py                 # LR, GBT, isotonic, Platt, metrics (numpy only)
    │
    ├── train.py                  # train on synthetic data
    ├── tune_gbt.py               # hyperparameter sweep
    ├── cv.py                     # 5-fold time-series cross-validation
    ├── inspect_model.py          # feature importance + top-20 risky team-weeks
    ├── threshold_tuning.py       # precision/recall at K — pick an action threshold
    ├── calibration_plot.py       # reliability diagram (ASCII + SVG)
    │
    ├── predict.py                # interactive CLI scorer (uses model_bundle.json)
    ├── checkin.py                # weekly survey CLI; appends to checkins.csv
    ├── load_real.py              # convert checkins.csv -> training-ready dataframe
    ├── train_real.py             # train on real data (with --blend for low data)
    ├── bundle_to_js.py           # export trained bundle for the web app
    │
    ├── test_pipeline.py          # smoke test: end-to-end run in <30s
    │
    ├── discovery.md              # checklist: what data does your org have?
    ├── survey_template.md        # form spec for a Google Form / Typeform
    │
    └── (artifacts written by train.py)
        ├── model_bundle.json     # current trained model
        ├── model_bundle.js       # JS-loadable copy for the web app
        ├── bundles/              # versioned copies, never overwritten
        ├── metrics.json          # test ROC-AUC / PR-AUC / Brier
        ├── feature_importance.csv
        ├── synthetic_data.csv
        ├── scored_teams.csv
        └── tune_results.csv
```

---

## The model in one paragraph

A latent "burnout reservoir" `R_t` accumulates pressure (long hours, high
stress, deadline pressure, low mood) minus recovery (sleep, manager
support, peer support, recent PTO). The label is sampled from
`Bernoulli(sigmoid(R_t - 1.6))`, giving roughly a 12% positive rate.
The model has to recover this from noisy signals + 4w/12w rolling means
+ engineered features (deltas, volatility, slopes, event-recency
indicators, interactions). On synthetic data, **logistic regression
hits ROC-AUC ≈ 0.78, Brier ≈ 0.09**, near the irreducible noise floor.

---

## Training & evaluating

```powershell
cd "outputs - Copy"

# Standard training run
python train.py

# Wider sweep of GBT hyperparameters (~5-10 min)
python tune_gbt.py

# 5-fold time-series cross-validation
python cv.py

# Pick an action threshold (e.g. "flag the top 10% of team-weeks")
python threshold_tuning.py

# Reliability diagram — does '30%' actually happen 30% of the time?
python calibration_plot.py

# See which teams scored highest, eyeball their signals
python inspect_model.py
```

---

## Collecting real data

### Option A — Use the web app

Open `checkin-app.html` in any browser, install it as a PWA on your
phone (menu → "Add to Home Screen" on mobile), check in weekly, then
export the CSV from the menu. The export schema matches what the
Python pipeline expects.

### Option B — Use the CLI

```powershell
cd "outputs - Copy"
python checkin.py --predict     # weekly: takes 30 seconds
```

Either way, when you have ≥80 rows + ≥10 positive labels:

```powershell
python train_real.py                # train on real data alone
python train_real.py --blend 60     # blend with 60 synthetic teams (low-data mode)
```

If you don't yet have 80 rows, start by reading `discovery.md` to find
out what passive telemetry your org might already have available
(calendar, Slack, GitHub, PagerDuty), and `survey_template.md` for the
exact wording of a 30-second weekly pulse.

---

## Connecting the web app to the trained model

By default the web app uses a hand-coded heuristic that mirrors the
data-generating process. To use your *actual* trained model:

```powershell
cd "outputs - Copy"
python bundle_to_js.py              # writes model_bundle.js
```

Then in the web app's menu: **Import model → pick `model_bundle.js`**.
The app caches it in `localStorage`. Header shows "trained model loaded"
once it's active.

---

## Sanity-checking everything still works

```powershell
cd "outputs - Copy"
python test_pipeline.py
```

Trains on a tiny dataset, scores, round-trips a CSV, and asserts the
metrics are sensible. Should finish in under 30 seconds. Run after any
edit to `scenarios.py` / `models.py` / `train.py`.

---

## Run order, in plain English

1. **First time on this machine:** `pip install -r requirements.txt`
2. **Build the model:** `python train.py` (in `outputs - Copy/`)
3. **Use it:** open `checkin-app.html` *or* run `python predict.py`
4. **Tune it:** `python tune_gbt.py`, then update `train.py` with the
   winning config and re-run.
5. **Make it predict on real data:** collect via `checkin.py` or the
   web app for ~12 weeks (with at least a handful of people), then
   `python train_real.py --blend 60`.
6. **Decide what to act on:** `python threshold_tuning.py` to pick a
   probability cutoff that matches your team's bandwidth for follow-up.

---

## What this is and isn't

- **It is** a self-reflection tool with a defensible model behind it,
  intended for personal use or for managers wanting to spot teams under
  sustained stress *before* anyone burns out.
- **It is not** a clinical diagnostic, an HR surveillance tool, or
  trained on real burnout data out of the box. Anyone making decisions
  based on its outputs should run `calibration_plot.py` first to see
  what its probabilities actually mean.
