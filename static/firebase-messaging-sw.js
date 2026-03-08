importScripts('https://www.gstatic.com/firebasejs/9.6.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.6.1/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyAdzJ3cJ7riBLGw9X89tPntQ6Q4MPbUewY",
  authDomain: "sgme-a4d52.firebaseapp.com",
  projectId: "sgme-a4d52",
  messagingSenderId: "929642581311",
  appId: "1:929642581311:web:d93240da819f2cef58d78a"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage(function(payload) {

  console.log("Push recebido:", payload);

  const notificationTitle = payload.notification.title;

  const notificationOptions = {
    body: payload.notification.body,
    icon: "/static/icon-192.png",
    badge: "/static/icon-192.png",
    data: {
      url: payload.data?.url || "/"
    }
  };

  self.registration.showNotification(notificationTitle, notificationOptions);

});

self.addEventListener('notificationclick', function(event) {

  event.notification.close();

  const url = event.notification.data?.url || "/";

  event.waitUntil(
    clients.openWindow(url)
  );

});