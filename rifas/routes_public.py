from flask import Blueprint, jsonify, render_template, request

from rifas.services import (
    RifaError,
    RifaSchemaMissingError,
    get_payment,
    payment_summary,
    process_webhook,
    purchase_rifas,
)


rifas_public_bp = Blueprint("rifas_public", __name__)


@rifas_public_bp.route("/rifas", methods=["GET"])
def rifas_home():
    return render_template("rifas_publica.html")


@rifas_public_bp.route("/rifas/comprar", methods=["POST"])
def comprar_rifa():
    data = request.get_json(silent=True) or request.form
    try:
        quantidade = int(data.get("quantidade_rifas", 0))
        resultado = purchase_rifas(
            nome=data.get("nome", ""),
            telefone=data.get("telefone", ""),
            email=data.get("email", ""),
            quantidade_rifas=quantidade,
        )
        return jsonify(resultado.asdict()), 201
    except ValueError:
        return jsonify({"erro": "Quantidade de rifas invalida."}), 400
    except RifaSchemaMissingError as exc:
        return jsonify({"erro": str(exc)}), 503
    except RifaError as exc:
        return jsonify({"erro": str(exc)}), 400


@rifas_public_bp.route("/rifas/pagamento/<payment_id>", methods=["GET"])
def pagamento_publico(payment_id):
    try:
        pagamento = get_payment(payment_id)
    except RifaSchemaMissingError as exc:
        return jsonify({"erro": str(exc)}), 503
    if pagamento is None:
        return jsonify({"erro": "Pagamento nao encontrado."}), 404
    return jsonify(payment_summary(pagamento))


@rifas_public_bp.route("/rifas/webhook/pix", methods=["POST"])
@rifas_public_bp.route("/webhook/pix", methods=["POST"])
def webhook_pix():
    payload = request.get_json(silent=True) or {}
    raw_body = request.get_data() or b""
    assinatura = request.headers.get("X-Webhook-Signature", "")
    try:
        pagamento = process_webhook(payload, raw_body, assinatura)
        return jsonify({"status": "ok", "pagamento_id": pagamento.id})
    except RifaSchemaMissingError as exc:
        return jsonify({"erro": str(exc)}), 503
    except RifaError as exc:
        return jsonify({"erro": str(exc)}), 400
