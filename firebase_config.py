import firebase_admin
from firebase_admin import credentials, messaging

cred = credentials.Certificate("firebase-key.json")
firebase_admin.initialize_app(cred)

def notificar_usuario(usuario, titulo, mensagem):
    if usuario.firebase_token and usuario.notificacoes_ativas:
        enviar_push(usuario.firebase_token, titulo, mensagem)

def enviar_push(token, titulo, mensagem):
    message = messaging.Message(
        notification=messaging.Notification(
            title=titulo,
            body=mensagem,
        ),
        token=token,
    )

    response = messaging.send(message)
    return response