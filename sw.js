const CACHE_NAME = 'matatu254-pwa-v3';
const OFFLINE_URL = '/offline/';

async function findShellAssets() {
  const response = await fetch('/', { credentials: 'omit', cache: 'no-store' });
  if (!response.ok) return [];
  const html = await response.text();
  const found = new Set();
  const tags = html.match(/<(?:link|script)\b[^>]*>/gi) || [];
  for (const tag of tags) {
    const href = tag.match(/\bhref=["']([^"']+)["']/i)?.[1];
    const src = tag.match(/\bsrc=["']([^"']+)["']/i)?.[1];
    const asset = href || src;
    if (asset && (tag.includes('stylesheet') || tag.includes('app-shell'))) {
      const url = new URL(asset, self.location.origin);
      if (url.origin === self.location.origin) found.add(url.href);
    }
  }
  const manifestHref = tags.map((tag) => tag.match(/\bhref=["']([^"']+)["']/i)?.[1])
    .find((href) => href && /manifest\.json/.test(href));
  if (manifestHref) {
    const manifestUrl = new URL(manifestHref, self.location.origin);
    found.add(manifestUrl.href);
    try {
      const manifestResponse = await fetch(manifestUrl, { credentials: 'omit', cache: 'no-store' });
      if (manifestResponse.ok) {
        const manifest = await manifestResponse.json();
        for (const icon of manifest.icons || []) {
          const iconUrl = new URL(icon.src, manifestUrl);
          if (iconUrl.origin === self.location.origin) found.add(iconUrl.href);
        }
      }
    } catch (_) {
      // The offline page remains available if optional manifest parsing fails.
    }
  }
  return [...found];
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    const offlineResponse = await fetch(OFFLINE_URL, { credentials: 'omit', cache: 'no-store' });
    if (offlineResponse.ok) await cache.put(OFFLINE_URL, offlineResponse);
    const assets = await findShellAssets().catch(() => []);
    await Promise.all(assets.map(async (asset) => {
      try {
        const response = await fetch(asset, { credentials: 'omit', cache: 'no-store' });
        if (response.ok) await cache.put(asset, response);
      } catch (_) {
        // A single optional asset must not prevent installing the offline shell.
      }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((key) => key.startsWith('matatu254-pwa-') && key !== CACHE_NAME)
      .map((key) => caches.delete(key)))
  ).then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const requestUrl = new URL(event.request.url);
  if (requestUrl.origin !== self.location.origin) return;

  // HTML is always fetched fresh; only the public, non-personalized offline route is cached.
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(async () =>
      (await caches.match(OFFLINE_URL)) || Response.error()
    ));
    return;
  }

  if (!requestUrl.pathname.startsWith('/static/')) return;
  event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request).then((response) => {
    if (response.ok) {
      const copy = response.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
    }
    return response;
  })));
});
