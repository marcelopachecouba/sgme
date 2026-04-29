from datetime import datetime
from flask import request, jsonify, Blueprint
from extensions import db
from rifas.models import PagamentoRifa, Rifa
import logging

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)

@api_bp.route("/webhook/pix/sicredi", methods=["POST"])
def webhook_pix_sicredi():
    payload = request.get_json(silent=True)

    if not payload:
        logger.warning("Webhook vazio")
        return jsonify({"msg": "ok"}), 200

    logger.info("Webhook recebido Sicredi")

    try:
        pix_list = payload.get("pix", [])

        if not pix_list:
            return jsonify({"msg": "ignorado"}), 200

        for pix in pix_list:
            txid = (pix.get("txid") or "").strip().upper()

            if not txid:
                continue

            if pix.get("valor") is None:
                continue

            pagamento = db.session.execute(
                db.select(PagamentoRifa).where(PagamentoRifa.txid == txid)
            ).scalar_one_or_none()

            if not pagamento:
                logger.warning(f"Pagamento não encontrado txid={txid}")
                continue

            if pagamento.status == "pago":
                logger.info(f"Webhook duplicado txid={txid}")
                continue

            pagamento.status = "pago"
            pagamento.data_pagamento = datetime.utcnow()

            rifas = db.session.execute(
                db.select(Rifa).where(Rifa.pagamento_id == pagamento.id)
            ).scalars().all()

            for rifa in rifas:
                rifa.status = "pago"

        db.session.commit()
        logger.info("Webhook processado com sucesso")

        return jsonify({"msg": "ok"}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro webhook: {str(e)}")
        return jsonify({"msg": "erro"}), 500