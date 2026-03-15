self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});


/* RECEBER PUSH */
self.addEventListener("push", function(event) {

  if (!event.data) return;

  const data = event.data.json();

  const title = data.title || "SGME";

  const options = {
    body: data.body || "",
    icon: "/static/img/icon-192.png",
    badge: "/static/img/badge.png",
    data: {
      url: data.url || "/"
    }
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );

});


/* CLICAR NA NOTIFICAÇÃO */
self.addEventListener("notificationclick", function(event) {

  const url = event.notification.data.url || "/";

  event.notification.close();

  event.waitUntil(

    clients.matchAll({
      type: "window",
      includeUncontrolled: true
    }).then(function(clientList) {

      for (const client of clientList) {

        if (client.url === url && "focus" in client) {
          return client.focus();
        }

      }

      if (clients.openWindow) {
        return clients.openWindow(url);
      }

    })

  );

});