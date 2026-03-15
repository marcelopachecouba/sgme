async function registrarPush() {

    const permission = await Notification.requestPermission();

    if (permission !== "granted") {
        return;
    }

    const token = await messaging.getToken();

    fetch("/api/salvar-token", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            token: token,
            device: "web"
        })
    });

}