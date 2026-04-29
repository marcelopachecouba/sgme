from datetime import datetime
from flask import request, jsonify
from app import db
from rifas.models import PagamentoRifa, Rifa
import logging

logger = logging.getLogger(__name__)

@api_bp.route("/webhook/pix/sicredi", methods=["POST"])
def webhook_pix_sicredi():
    payload = request.get_json(silent=True)

    if not payload:
        logger.warning("Webhook vazio")
        return jsonify({"msg": "ok"}), 200

    logger.info(f"Webhook recebido: {payload}")

    try:
        # 🔎 padrão Sicredi
        pix_list = payload.get("pix", [])

        if not pix_list:
            return jsonify({"msg": "ignorado"}), 200

        for pix in pix_list:
            txid = pix.get("txid")

            if not txid:
                continue

            pagamento = db.session.execute(
                db.select(PagamentoRifa).where(PagamentoRifa.txid == txid)
            ).scalar_one_or_none()

            if not pagamento:
                logger.warning(f"Pagamento não encontrado txid={txid}")
                continue

            # 🔒 idempotência (não processar duas vezes)
            if pagamento.status == "pago":
                logger.info(f"Webhook duplicado txid={txid}")
                continue

            # ✅ marca como pago
            pagamento.status = "pago"
            pagamento.data_pagamento = datetime.utcnow()

            # 🔥 libera rifas
            rifas = db.session.execute(
                db.select(Rifa).where(Rifa.pagamento_id == pagamento.id)
            ).scalars().all()

            for rifa in rifas:
                rifa.status = "pago"

        db.session.commit()

        return jsonify({"msg": "ok"}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro webhook: {str(e)}")
        return jsonify({"msg": "erro"}), 500