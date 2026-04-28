from flask import request, jsonify
from datetime import datetime
from extensions import db
from models import PagamentoRifa, Rifa
from rifas.payments import SicrediPixGateway
import logging

from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api")

logger = logging.getLogger(__name__)

from rifas.services import process_webhook, validate_webhook_signature

@api_bp.route("/webhook/pix/sicredi", methods=["POST"])
def webhook_pix_sicredi():

    # 🔒 RAW BODY (OBRIGATÓRIO)
    raw_body = request.get_data()
    signature = request.headers.get("X-Webhook-Signature")

    # 🔒 SEGURANÇA
    if not validate_webhook_signature(raw_body, signature):
        logger.warning(f"Webhook assinatura inválida IP={request.remote_addr}")
        return jsonify({"msg": "assinatura invalida"}), 403

    # 🔽 PAYLOAD
    payload = request.get_json(silent=True)

    if not payload:
        logger.warning("Webhook vazio recebido")
        return jsonify({"msg": "payload vazio"}), 200

    # 🔍 LOG BÁSICO (debug produção)
    user_agent = request.headers.get("User-Agent", "")
    logger.info(f"Webhook recebido IP={request.remote_addr} UA={user_agent}")

    try:
        # 🔥 PROCESSAMENTO CENTRAL (ESSENCIAL)
        pagamento = process_webhook(payload, raw_body, signature)

        db.session.commit()

        logger.info(
            f"Pagamento confirmado via webhook | txid={pagamento.txid} | id={pagamento.id}"
        )

        return jsonify({"msg": "ok"}), 200

    except Exception as e:
        db.session.rollback()

        logger.error(
            f"Erro webhook Sicredi | erro={str(e)} | payload={payload}"
        )

        return jsonify({"msg": "erro interno"}), 500