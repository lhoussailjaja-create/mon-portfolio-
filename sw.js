const VERSION = 'v29';
const CACHE_NAME = `mon-portfolio-${VERSION}`;

// V29: invalidate the old V28 cache and take control immediately.
self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

// V29 deliberately does not cache the app shell.
// This prevents an old cached index.html from being served again.
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  event.respondWith(fetch(event.request));
});
