const CACHE_NAME = "postflow-v2";
const STATIC_ASSETS = [
  "/",
  "/calendar/",
  "/hashtag-groups/",
  "/drafts/",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(STATIC_ASSETS).catch(function () {
        // Silently fail if offline during install
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(
        names
          .filter(function (name) { return name !== CACHE_NAME; })
          .map(function (name) { return caches.delete(name); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", function (event) {
  var request = event.request;

  // Skip non-GET requests
  if (request.method !== "GET") return;

  // Skip external requests
  if (!request.url.startsWith(self.location.origin)) return;

  // Network-first for HTML pages (always try fresh content)
  if (request.headers.get("accept") && request.headers.get("accept").includes("text/html")) {
    event.respondWith(
      fetch(request)
        .then(function (response) {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(request, clone);
          });
          return response;
        })
        .catch(function () {
          return caches.match(request).then(function (cached) {
            return cached || caches.match("/");
          });
        })
    );
    return;
  }

  // Cache-first for static assets (JS, CSS, images)
  if (request.url.match(/\.(js|css|png|jpg|jpeg|svg|ico|woff2?)$/)) {
    event.respondWith(
      caches.match(request).then(function (cached) {
        if (cached) return cached;
        return fetch(request).then(function (response) {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(request, clone);
          });
          return response;
        });
      })
    );
    return;
  }

  // Network-first for API/other requests
  event.respondWith(
    fetch(request).catch(function () {
      return caches.match(request);
    })
  );
});
