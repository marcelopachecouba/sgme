import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import { getMessaging, getToken, onMessage } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging.js";

const config = window.sgmeFirebaseConfig || {};

if (!config.vapidKey) {
  // Firebase sem VAPID configurada: desativa apenas o push web.
} else {
  const app = initializeApp({
    apiKey: config.apiKey,
    authDomain: config.authDomain,
    projectId: config.projectId,
    messagingSenderId: config.messagingSenderId,
    appId: config.appId,
  });

  const messaging = getMessaging(app);

  Notification.requestPermission().then((permission) => {
    if (permission !== "granted") {
      return null;
    }

    return getToken(messaging, { vapidKey: config.vapidKey });
  }).then((currentToken) => {
    if (!currentToken) {
      return;
    }

    const tokenSalvo = localStorage.getItem("firebase_token");
    if (tokenSalvo === currentToken) {
      return;
    }

    return fetch("/salvar-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: currentToken }),
    }).then(() => {
      localStorage.setItem("firebase_token", currentToken);
    });
  }).catch((error) => {
    console.error("Falha ao inicializar notificacoes Firebase:", error);
  });

  onMessage(messaging, (payload) => {
    const url = payload?.data?.url || "/";
    const notification = new Notification(payload.notification.title, {
      body: payload.notification.body,
      data: { url },
    });

    notification.onclick = function abrirDestino() {
      window.location.href = url;
    };
  });
}
