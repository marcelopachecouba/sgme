from datetime import datetime
from flask import request, jsonify, Blueprint
from extensions import db
from rifas.models import PagamentoRifa, Rifa
import logging
import json
logger = logging.getLogger(__name__)

api_bp = Blueprint("rifas_api", __name__)

from decimal import Decimal

@api_bp.route("/webhook/pix/sicredi", methods=["POST"])
def webhook_pix_sicredi():
    payload = request.get_json(silent=True)

    if not payload:
        logger.warning("Webhook vazio")
        return jsonify({"msg": "ok"}), 200

    pix_list = payload.get("pix", [])
    logger.info(f"Webhook recebido Sicredi | itens={len(pix_list)}")

    try:
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

            # 🔒 idempotência por status
            if pagamento.status == "pago":
                logger.info(f"Webhook duplicado txid={txid}")
                continue

            # 🔒 idempotência extra (endToEndId)
            end_to_end = pix.get("endToEndId")
            if end_to_end and pagamento.end_to_end_id == end_to_end:
                logger.info(f"Webhook duplicado endToEndId={end_to_end}")
                continue

            # ✅ atualizar pagamento
            pagamento.status = "pago"
            pagamento.tipo_pagamento = "pix_auto"
            pagamento.data_pagamento = datetime.utcnow()

            pagamento.valor_pago = Decimal(pix.get("valor"))
            pagamento.banco_payload = json.dumps(pix, ensure_ascii=False)
            pagamento.end_to_end_id = end_to_end

            # 🔥 liberar rifas
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
        
@api_bp.route("/rifas/status/<int:pagamento_id>")
def status_pagamento(pagamento_id):
    pagamento = db.session.get(PagamentoRifa, pagamento_id)

    if not pagamento:
        return {"status": "erro"}, 404

    if pagamento.status == "pago":
        campanha = pagamento.campanha.titulo

        rifas = db.session.execute(
            db.select(Rifa).where(Rifa.pagamento_id == pagamento.id)
        ).scalars().all()

        numeros = ", ".join([str(r.numero).zfill(4) for r in rifas])

        valor = f"{pagamento.valor_total:.2f}".replace(".", ",")
        data_sorteio = pagamento.campanha.data_sorteio.strftime("%d/%m/%Y")

        mensagem = (
            f"🎉 Pagamento confirmado com sucesso!\n\n"
            f"Olá {pagamento.cliente.nome}, tudo bem? 😊\n\n"
            f"Sua participação na {campanha} foi confirmada!\n\n"
            f"🎟️ Seus números: {numeros}\n"
            f"💰 Valor pago: R$ {valor}\n"
            f"📅 Sorteio final: {data_sorteio}\n\n"
            f"🙏 Muito obrigado e boa sorte! 🍀"
        )

        return {
            "status": "pago",
            "mensagem": mensagem
        }

    return {"status": pagamento.status}