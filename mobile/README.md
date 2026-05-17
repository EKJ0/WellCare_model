# WellCare Mobile (Expo wrapper)

This is a thin Expo / React Native app that loads the WellCare check-in PWA
in a `WebView`. The actual UI lives in the parent project's `checkin-app.html`
and is served via the URL configured in `App.tsx`.

## Setup

```powershell
cd mobile
npm install
```

## Configure the URL

Open `App.tsx` and replace the `PWA_URL` constant with the URL where you've
deployed `checkin-app.html` (e.g. Netlify, Vercel, GitHub Pages, your own
server). The URL **must** be HTTPS.

```ts
const PWA_URL = 'https://your-site.netlify.app';
```

## Build an Android APK with EAS

```powershell
# One-time
npx eas-cli@latest login
npx eas-cli@latest init       # links this project to your Expo account, fills projectId in app.json

# Each build
npx eas-cli@latest build --platform android --profile preview
```

When the build finishes (~10-20 min on Expo's servers), EAS prints a URL.
Open that URL on your Android phone, download the APK, and install
(you'll need to allow "Install unknown apps" for your browser).

## Testing locally without a build

```powershell
npx expo start
```

Scan the QR with the Expo Go app on your phone. Note: this still loads the
PWA from the URL, so make sure the URL is reachable from your phone.

## Updating

If you change `checkin-app.html`, redeploy the PWA — the WebView will pick
up the new version on next launch (the SW is configured network-first for
the HTML). You only need to rebuild the APK if you change something in
`App.tsx` or the Expo config.
