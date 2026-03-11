self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("notificationclick", (event) => {
  const url = event.notification?.data?.url || "/";

  event.notification.close();
  event.waitUntil(clients.openWindow(url));
});
