# WellCare Stress / Academic Burnout-Risk Prototype

A student- and young-adult-focused burnout-risk check-in prototype you can run
locally. The app tracks self-reported patterns related to stress, emotional
overload, academic pressure, and recovery. It is not a diagnostic or clinical
tool and does not diagnose depression, anxiety, burnout, or any medical
condition.

The current app is intentionally still a standalone single-file React PWA
(`checkin-app.html`) for university demo speed. Longer term, migrate it to a
Vite/React app with `src/components`, `src/screens`, `src/lib`, `src/model`,
`src/storage`, and `src/styles`.

---

Current product direction:

- Keep `checkin-app.html` as the main working demo app for now.
- `archive/checkin-app.jsx` is an archived simple mock and should not be used
  as the source of truth.
- The MVP is individual-first: user downloads app, tracks themselves over time,
  WellCare learns their personal baseline, then shows non-diagnostic stress /
  academic burnout-risk insights.
- Care Circle, tracker sharing, trusted-person nudges, and family/couple sharing
  are optional future/support features. They are not the core user journey.
- Daily check-ins collect stress, energy, sleep, overwhelm/work pressure, focus,
  motivation, recovery time, social battery, social interaction quality,
  optional substance-use context, and optional short journaling.
- Daily Tracker entries produce a Recovery Status from sleep quality, movement,
  breaks, real rest, screen-time context, social connection, and substance-use
  context. Context/habits are small modifiers, not the main risk engine.

Next recommended steps:

1. Keep the standalone PWA for the next demo, then migrate to React/Vite when
   the screen flows stabilize. See `docs/ARCHITECTURE.md`.
2. Replace prototype localStorage sync with authenticated cloud storage for
   users, check-ins, daily tracker context, baseline summaries, weekly summaries,
   and anonymized exports.
3. Add app-level tests for scoring, context-aware habit modifiers, personal
   baseline behavior, privacy/export boundaries, and optional sharing settings.


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
├── docs/                         # architecture and migration notes
├── database/                     # cloud schema foundation
├── server/                       # prototype invite server
└── outputs - Copy/               # the Python ML pipeline
    │
    ├── scenarios.py              # synthetic data generator + feature engineering
    ├── models.py                 # LR, GBT, isotonic, Platt, metrics (numpy only)
    │
    ├── train.py                  # train on synthetic data
    ├── tune_gbt.py               # hyperparameter sweep
    ├── cv.py                     # 5-fold time-series cross-validation
    ├── inspect_model.py          # feature importance + top risky synthetic rows
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
        ├── scored_people.csv / scored_teams.csv
        └── tune_results.csv
```

---

## The model in one paragraph

A latent "burnout reservoir" `R_t` accumulates pressure (heavy study/workload
hours, high stress, exam or assignment pressure, low mood) minus recovery
(sleep, supportive connection, peer support, recent recovery days). The label is sampled from
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

# Pick an action threshold (e.g. "flag the top 10% of high-risk check-ins")
python threshold_tuning.py

# Reliability diagram — does '30%' actually happen 30% of the time?
python calibration_plot.py

# See which synthetic rows scored highest, eyeball their signals
python inspect_model.py
```

---

## Optional: Run the invite server (prototype)

The demo includes a small Express server that issues signed, time-limited invite tokens and persists invites/connections to `server/data/db.json`.

1. Install and start the server:

```powershell
cd server
npm install
npm start
```

2. The web app will try the server at `/api/invite/*` automatically and fall back to a local client-only invite format if the server is unreachable.

Security: the server uses an HMAC secret (`WELLCARE_SECRET` in `.env`) to sign
tokens. Invite privacy settings are carried through acceptance, shared tracker
reads require a connected viewer identity, and the raw debug database endpoint
is hidden unless `WELLCARE_ENABLE_DEBUG_DB=true`. This prototype still stores
data in a JSON file; replace with Postgres and proper auth for production.

### Run the server tests

```powershell
cd server
npm test
```

This verifies the invite creation and accept flow and checks the file-backed JSON persistence.

---

## Collecting real data

### Option A — Use the web app

Open `checkin-app.html` in any browser, install it as a PWA on your
phone (menu → "Add to Home Screen" on mobile), check in daily or weekly, then
export the CSV from the menu. The export schema matches what the
Python pipeline expects.

### Option B — Use the CLI

```powershell
cd "outputs - Copy"
python checkin.py --predict     # quick pulse: takes 30 seconds
```

Either way, when you have ≥80 rows + ≥10 positive labels:

```powershell
python train_real.py                # train on real data alone
python train_real.py --blend 60     # blend with synthetic rows (low-data mode)
```

If you don't yet have 80 rows, start by reading `discovery.md` to find
out what passive context data may be useful later
(calendar load, deadlines, sleep/recovery logs), and `survey_template.md` for the
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
   web app for several weeks (with enough check-ins to calibrate), then
   `python train_real.py --blend 60`.
6. **Decide what to act on:** `python threshold_tuning.py` to pick a
   probability cutoff that matches your support bandwidth for follow-up.

---

## What this is and isn't

- **It is** a self-reflection tool with a defensible prototype model behind it,
  intended for personal stress, recovery, and academic burnout-risk tracking.
- **It is not** a diagnostic or medical tool. Anyone using the model for
  research should run `calibration_plot.py` first to see what its probabilities
  actually mean.
