import json
import logging
import os

import firebase_admin
from firebase_admin import credentials, messaging


firebase_ativo = False
logger = logging.getLogger(__name__)


def iniciar_firebase():
    global firebase_ativo

    cred_env = os.environ.get("FIREBASE_CREDENTIALS")
    if not cred_env:
        logger.warning("FIREBASE_CREDENTIALS nao encontrada")
        return

    try:
        firebase_dict = json.loads(cred_env)
        cred = credentials.Certificate(firebase_dict)

        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)

        firebase_ativo = True
        logger.info("Firebase iniciado com sucesso")
    except Exception as e:
        logger.exception("Erro ao iniciar Firebase: %s", e)


def enviar_push(token, titulo, mensagem):
    if not firebase_ativo:
        logger.warning("Firebase nao ativo")
        return

    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=titulo,
                body=mensagem,
            ),
            token=token,
        )
        messaging.send(message)
        logger.info("Push enviado")
    except Exception as e:
        logger.exception("Erro push: %s", e)
