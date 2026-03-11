import { getApp, getApps, initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import { getMessaging, getToken, onMessage } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging.js";

const config = window.sgmeFirebaseConfig || {};
let pushListenerRegistrado = false;

async function solicitarPermissaoPushInterna() {
  if (!config.vapidKey) {
    console.warn("Firebase sem VAPID configurada.");
    return false;
  }

  const app = getApps().length
    ? getApp()
    : initializeApp({
        apiKey: config.apiKey,
        authDomain: config.authDomain,
        projectId: config.projectId,
        messagingSenderId: config.messagingSenderId,
        appId: config.appId,
      });

  const messaging = getMessaging(app);
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    return false;
  }

  const currentToken = await getToken(messaging, { vapidKey: config.vapidKey });
  if (!currentToken) {
    return false;
  }

  const tokenSalvo = localStorage.getItem("firebase_token");
  if (tokenSalvo !== currentToken) {
    await fetch("/salvar-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: currentToken }),
    });
    localStorage.setItem("firebase_token", currentToken);
  }

  if (!pushListenerRegistrado) {
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
    pushListenerRegistrado = true;
  }

  return true;
}

window.solicitarPermissaoPush = function solicitarPermissaoPush() {
  solicitarPermissaoPushInterna()
    .then((ok) => {
      if (ok) {
        alert("Notificacoes push ativadas com sucesso.");
      } else {
        alert("Nao foi possivel ativar as notificacoes push.");
      }
    })
    .catch((error) => {
      console.error("Falha ao inicializar notificacoes Firebase:", error);
      alert("Falha ao ativar notificacoes push.");
    });
};

if (!config.vapidKey) {
  // Firebase sem VAPID configurada: desativa apenas o push web.
} else {
  solicitarPermissaoPushInterna().catch((error) => {
    console.error("Falha ao inicializar notificacoes Firebase:", error);
  });
}
