from datetime import datetime
from flask import request, jsonify, Blueprint
from extensions import db
from rifas.models import PagamentoRifa, Rifa
import logging
import json
from rifas.services import montar_mensagem_pagamento

logger = logging.getLogger(__name__)


from flask import Blueprint
rifas_api_bp = Blueprint("rifas_api", __name__, url_prefix="/api")


@rifas_api_bp.route("/pagamento/status/<payment_id>")
def pagamento_status(payment_id):
    pagamento = db.session.execute(
        db.select(PagamentoRifa).where(PagamentoRifa.id == payment_id)
    ).scalar_one_or_none()

    if not pagamento:
        return jsonify({"erro": "nao encontrado"}), 404

    try:
        mensagem = montar_mensagem_pagamento(pagamento)
    except Exception as e:
        mensagem = None

    return jsonify({
        "status": pagamento.status,
        "tipo": pagamento.tipo_pagamento,
        "mensagem": mensagem,
        "telefone": pagamento.cliente.telefone
    })



from decimal import Decimal

from datetime import datetime
from decimal import Decimal
import json

@rifas_api_bp.route("/webhook/pix/sicredi", methods=["POST"])
def webhook_pix_sicredi():
    payload = request.get_json(silent=True)

    if not payload:
        logger.warning("Webhook vazio")
        return jsonify({"msg": "ok"}), 200

    pix_list = payload.get("pix", [])
    logger.info(f"Webhook recebido Sicredi | itens={len(pix_list)}")

    if not pix_list:
        return jsonify({"msg": "ignorado"}), 200

    try:
        for pix in pix_list:
            txid = (pix.get("txid") or "").strip().upper()

            if not txid or pix.get("valor") is None:
                continue

            # 🔒 lock no registro
            pagamento = db.session.execute(
                db.select(PagamentoRifa).where(PagamentoRifa.txid == txid)
            ).scalar_one_or_none()

            if not pagamento:
                logger.warning(f"Pagamento não encontrado txid={txid}")
                continue

            # 🔒 idempotência
            if pagamento.status == "pago":
                logger.info(f"Webhook duplicado txid={txid}")
                continue

            end_to_end = pix.get("endToEndId")

            if end_to_end and pagamento.end_to_end_id == end_to_end:
                logger.info(f"Webhook duplicado endToEndId={end_to_end}")
                continue

            # ✅ atualizar pagamento
            pagamento.status = "pago"
            pagamento.tipo_pagamento = "pix_auto"
            pagamento.data_pagamento = datetime.utcnow()

            try:
                pagamento.valor_pago = Decimal(str(pix.get("valor")))
            except:
                pagamento.valor_pago = Decimal("0.00")

            pagamento.banco_payload = json.dumps(pix, ensure_ascii=False)
            pagamento.end_to_end_id = end_to_end

            # 🔥 liberar rifas
            rifas = db.session.execute(
                db.select(Rifa).where(Rifa.pagamento_id == pagamento.id)
            ).scalars().all()

            for rifa in rifas:
                rifa.status = "pago"

            logger.info(f"Pagamento confirmado txid={txid} valor={pagamento.valor_pago}")

        db.session.commit()

        return jsonify({"msg": "ok"}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro webhook: {str(e)}")
        return jsonify({"msg": "erro"}), 500