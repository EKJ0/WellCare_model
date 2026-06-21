/* Burnout Check-in service worker.
 *
 * Cache strategy: stale-while-revalidate for the app shell so the app
 * loads instantly offline, but always tries the network in the
 * background to pick up updates.
 *
 * The check-in data itself lives in localStorage (not in the cache),
 * so users keep their history regardless of cache state.
 */

// Bump this whenever the HTML/CSS copy changes meaningfully so old
// installs drop their stale shell. We also use a network-first
// strategy for the HTML itself (see fetch handler) so even before
// the new SW activates, the page contents update.
const CACHE = 'wellcare-checkin-v5';
const SHELL = [
  './checkin-app.html',
  './manifest.webmanifest',
  // Optional model bundle, if it exists (written next to this file
  // by `python "outputs - Copy/bundle_to_js.py"`).
  './model_bundle.js',
  // CDN libraries the app loads
  'https://unpkg.com/react@18/umd/react.production.min.js',
  'https://unpkg.com/react-dom@18/umd/react-dom.production.min.js',
  'https://unpkg.com/@babel/standalone/babel.min.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // Cache what we can; ignore individual failures (model_bundle.js
      // may not exist before the user runs bundle_to_js.py).
      Promise.all(SHELL.map((url) =>
        cache.add(url).catch(() => null)
      ))
    )
  );
  self.skipWaiting();
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);

  // For navigation requests and the main HTML file, prefer the network so
  // copy/UI updates land immediately. Fall back to cache only if offline.
  const isHtml =
    event.request.mode === 'navigate' ||
    url.pathname.endsWith('/') ||
    url.pathname.endsWith('checkin-app.html') ||
    url.pathname.endsWith('model_bundle.js');

  if (isHtml) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          if (res && res.status === 200) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(event.request, copy));
          }
          return res;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Everything else: stale-while-revalidate.
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const networked = fetch(event.request)
        .then((res) => {
          if (res && res.status === 200) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(event.request, copy));
          }
          return res;
        })
        .catch(() => cached);
      return cached || networked;
    })
  );
});
