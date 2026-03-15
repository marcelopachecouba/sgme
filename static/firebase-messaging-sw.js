self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});


self.addEventListener("push", function(event) {

  if (!event.data) return;

  const payload = event.data.json();

  const title =
    payload.title ||
    payload.notification?.title ||
    "SGME";

  const body =
    payload.body ||
    payload.notification?.body ||
    "";

  const url =
    payload.url ||
    payload.data?.url ||
    "/";

  const options = {
    body: body,
    icon: "/static/img/icon-192.png",
    badge: "/static/img/badge.png",
    vibrate: [200, 100, 200],
    requireInteraction: true,
    data: { url }
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );

});


self.addEventListener("notificationclick", function(event) {

  const url = event.notification.data.url || "/";

  event.notification.close();

  event.waitUntil(
    clients.matchAll({
      type: "window",
      includeUncontrolled: true
    }).then(function(clientList) {

      for (const client of clientList) {
        if (client.url.includes(url) && "focus" in client) {
          return client.focus();
        }
      }

      return clients.openWindow(url);

    })
  );

});