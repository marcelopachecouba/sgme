const CACHE_NAME = "sgme-cache-v1";

const urlsToCache = [
  "/",
  "/static/icon-192.png",
  "/static/icon-512.png"
];

// INSTALAÇÃO
self.addEventListener("install", function(event) {

  event.waitUntil(

    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(urlsToCache);
    })

  );

});

// CACHE OFFLINE
self.addEventListener("fetch", function(event) {

  event.respondWith(

    caches.match(event.request).then(function(response) {

      return response || fetch(event.request);

    })

  );

});

// NOTIFICAÇÃO
self.addEventListener("notificationclick", function(event) {

  const url = event.notification.data.url;

  event.notification.close();

  event.waitUntil(

    clients.openWindow(url)

  );

});