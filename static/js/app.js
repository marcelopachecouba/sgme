if ("serviceWorker" in navigator) {
  navigator.serviceWorker
    .register("/firebase-messaging-sw.js?v=20260311-1")
    .catch((error) => console.error("Falha ao registrar service worker:", error));
}

let deferredPrompt = null;

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredPrompt = event;

  const button = document.getElementById("btnInstalar");
  if (button) {
    button.style.display = "block";
  }
});

window.instalarApp = function instalarApp() {
  if (!deferredPrompt) {
    return;
  }

  deferredPrompt.prompt();
  deferredPrompt.userChoice.finally(() => {
    deferredPrompt = null;

    const button = document.getElementById("btnInstalar");
    if (button) {
      button.style.display = "none";
    }
  });
};
