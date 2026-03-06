importScripts('https://www.gstatic.com/firebasejs/9.6.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.6.1/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "SAIzaSyAdzJ3cJ7riBLGw9X89tPntQ6Q4MPbUewY",
  authDomain: "sgme-a4d52.firebaseapp.com",
  projectId: "sgme-a4d52",
  messagingSenderId: "sgme-a4d52",
  appId: "1:929642581311:web:d93240da819f2cef58d78a"
});

const messaging = firebase.messaging();