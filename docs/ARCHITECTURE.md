# WellCare Architecture Notes

## Current Decision

Keep `checkin-app.html` as the standalone demo app for now.

This is the best fit for the next university/demo milestone because it is easy
to open, easy to test, and does not add a build step. The app is already a
single-file React PWA with `manifest.webmanifest`, `sw.js`, and the optional
`model_bundle.js` scorer.

## Next Architecture

When the individual tracking and baseline-learning flows stabilize, migrate
the app to React/Vite:

```text
app/
  src/
    components/
    screens/
    lib/
    model/
    storage/
    styles/
```

Suggested first extraction:

- `screens/HomeScreen.jsx`
- `screens/InsightsScreen.jsx`
- `screens/TrackerScreen.jsx`
- `screens/ProfileScreen.jsx`
- `model/scoring.js`
- `model/personalBaseline.js`
- `model/trackerContext.js`
- `storage/localPrototypeStore.js`
- `storage/cloudStore.js`
- `lib/invites.js` and `lib/notifications.js` later, when optional sharing is
  intentionally reintroduced

## Data Model Direction

Prototype storage still uses `localStorage`, but the cloud schema should be the
source of truth for the personal tracking product:

- `auth.users` or provider-managed users
- `wellcare_profiles`
- `wellcare_checkins`
- `wellcare_daily_tracker_context`
- `wellcare_weekly_summaries`
- `wellcare_model_baselines`
- `wellcare_exports`

Optional future sharing tables can be added later for connections, invites,
shared tracker settings, notifications, and high-strain nudges. Private answers,
notes, exact habit details, and sensitive explanations stay private unless the
user explicitly enables sharing.

## Testing Direction

Before the React migration, keep server tests focused on the adaptive scoring
rules and the remaining optional invite behavior. After migration, add:

- Vitest tests for scoring and context modifiers
- Vitest tests for personal baseline adjustment and recovery drag
- React Testing Library tests for onboarding, daily check-in, tracker, weekly
  summaries, and privacy/export controls
- Playwright tests for the daily personal tracking journey
