# WellCare Architecture Notes

## Current Decision

Keep `checkin-app.html` as the standalone demo app for now.

This is the best fit for the next university/demo milestone because it is easy
to open, easy to test, and does not add a build step. The app is already a
single-file React PWA with `manifest.webmanifest`, `sw.js`, and the optional
`model_bundle.js` scorer.

## Next Architecture

When the Care Circle flows stabilize, migrate the app to React/Vite:

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
- `screens/CareCircleScreen.jsx`
- `screens/TrackerScreen.jsx`
- `screens/ProfileScreen.jsx`
- `model/scoring.js`
- `model/trackerContext.js`
- `storage/localPrototypeStore.js`
- `storage/cloudStore.js`
- `lib/invites.js`
- `lib/notifications.js`

## Data Model Direction

Prototype storage still uses `localStorage`, but the cloud schema should be the
source of truth for the connected product:

- `auth.users` or provider-managed users
- `wellcare_profiles`
- `wellcare_checkins`
- `wellcare_connections`
- `wellcare_connection_invites`
- `wellcare_shared_tracker_settings`
- `wellcare_alert_settings`
- `wellcare_notifications`
- `wellcare_alert_events`

Only accepted connections should receive alerts or see shared tracker data.
Default sharing is limited to risk percentage, risk level, trend, and last
check-in time. Private answers, notes, exact habit details, and sensitive
explanations stay private unless explicitly enabled.

## Testing Direction

Before the React migration, keep server tests focused on invite behavior and
connection defaults. After migration, add:

- Vitest tests for scoring and context modifiers
- React Testing Library tests for Care Circle and privacy controls
- Playwright tests for invite-link acceptance and notification flows

