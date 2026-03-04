import firebase_admin
from firebase_admin import credentials, messaging
import json
import os

firebase_ativo = False

def iniciar_firebase():

    global firebase_ativo

    if os.environ.get("FIREBASE_CREDENTIALS"):

        try:

            firebase_dict = json.loads(os.environ["FIREBASE_CREDENTIALS"])
            cred = credentials.Certificate(firebase_dict)

            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)

            firebase_ativo = True
            print("🔥 Firebase iniciado com sucesso")

        except Exception as e:
            print("❌ Erro ao iniciar Firebase:", e)

    else:
        print("⚠️ FIREBASE_CREDENTIALS não encontrada")


def enviar_push(token, titulo, mensagem):

    if not firebase_ativo:
        print("⚠️ Firebase não ativo")
        return

    try:

        message = messaging.Message(
            notification=messaging.Notification(
                title=titulo,
                body=mensagem
            ),
            token=token
        )

        messaging.send(message)

        print("✅ Push enviado")

    except Exception as e:
        print("❌ Erro push:", e)