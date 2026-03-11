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


def enviar_push(token, titulo, mensagem, url=None):

    if not firebase_ativo:
        logger.warning("Firebase nao ativo")
        return

    try:

        data_payload = {}

        if url:
            data_payload["url"] = url

        message = messaging.Message(
            notification=messaging.Notification(
                title=titulo,
                body=mensagem,
            ),
            data=data_payload,
            token=token,
        )

        messaging.send(message)
        logger.info("Push enviado")

    except Exception as e:
        logger.exception("Erro push: %s", e)


from firebase_admin import messaging
from models import Ministro


def enviar_notificacao_ministros(titulo, mensagem, ministros_ids):

    tokens = []

    ministros = Ministro.query.filter(Ministro.id.in_(ministros_ids)).all()

    for m in ministros:
        if m.firebase_token:
            tokens.append(m.firebase_token)

    if not tokens:
        return

    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=titulo,
            body=mensagem
        ),
        tokens=tokens
    )

    messaging.send_multicast(message)
