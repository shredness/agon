// Cache version — bump this on every deploy to force SW update
// This is intentionally a timestamp so CI/CD can inject it automatically
const CACHE = 'agon-v0.7.5';

const PRECACHE = [
  '/icon-192.png',
  '/icon-512.png',
  '/icon-180.png',
  '/icon-32.png',
  '/icon-16.png',
  '/favicon.ico',
  '/manifest.json',
];

self.addEventListener('install', e => {
  // Pre-cache static assets only (not index.html — always fetch fresh)
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(PRECACHE))
      .then(() => self.skipWaiting())  // activate immediately, don't wait for old SW to die
  );
});

self.addEventListener('activate', e => {
  // Delete all old caches
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())  // take control of all open tabs immediately
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // API calls: network only, no caching
  if (url.pathname.startsWith('/api/')) {
    return;  // let browser handle normally
  }

  // HTML (index.html / root): network-first, fall back to cache
  // This ensures users always get the latest app after a deploy
  if (e.request.mode === 'navigate' || url.pathname === '/' || url.pathname.endsWith('.html')) {
    e.respondWith(
      fetch(e.request)
        .then(resp => {
          // Update cache with fresh response
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
          return resp;
        })
        .catch(() => caches.match(e.request))  // offline fallback
    );
    return;
  }

  // Static assets (icons, manifest): cache-first, these rarely change
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(resp => {
        if (resp && resp.status === 200 && e.request.method === 'GET') {
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return resp;
      });
    })
  );
});
