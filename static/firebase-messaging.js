import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import { getMessaging, getToken } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging.js";

const firebaseConfig = {
  apiKey: "AIzaSyAdzJ3cJ7riBLGw9X89tPntQ6Q4MPbUewY",
  authDomain: "sgme-a4d52.firebaseapp.com",
  projectId: "sgme-a4d52",
  messagingSenderId: "929642581311",
  appId: "1:929642581311:web:d93240da819f2cef58d78a"
};

const app = initializeApp(firebaseConfig);
const messaging = getMessaging(app);

Notification.requestPermission().then((permission) => {
  if (permission === "granted") {
    getToken(messaging, { vapidKey: "BHI9GSKmwrXgTvOHwknqyr6Y2DM5RGT0N9CfOysUsCf3th_9k3zLtpr8NQRRrw9uVULE_A-usEoeZFnDLNiRQYY" })
      .then((currentToken) => {
        if (currentToken) {
          fetch("/salvar-token", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: currentToken })
          });
        }
      });
  }
});