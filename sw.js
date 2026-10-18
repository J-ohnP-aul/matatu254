const CACHE_NAME = 'matatu254-pwa-v1';
const CORE_ASSETS = [
  '/',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }

      return fetch(event.request)
        .then((networkResponse) => {
          const clonedResponse = networkResponse.clone();
          const requestUrl = new URL(event.request.url);
          const isSameOrigin = requestUrl.origin === self.location.origin;
          const shouldCache =
            requestUrl.pathname.startsWith('/static/') ||
            requestUrl.pathname.startsWith('/media/') ||
            event.request.mode === 'navigate';

          if (isSameOrigin && shouldCache) {
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clonedResponse));
          }

          return networkResponse;
        })
        .catch(() => caches.match('/') || caches.match('/manifest.json'));
    })
  );
});
