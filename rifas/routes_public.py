from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file

from rifas.services import (
    RifaError,
    RifaSchemaMissingError,
    get_payment,
    get_public_page_data,
    payment_summary,
    process_webhook,
    purchase_rifas,
    save_receipt,
)


rifas_public_bp = Blueprint("rifas_public", __name__)


@rifas_public_bp.route("/rifas", methods=["GET"])
def rifas_home():
    try:
        dados = get_public_page_data()
    except RifaSchemaMissingError as exc:
        dados = {"campanha": None, "disponiveis": 0, "vendidos": 0, "schema_message": str(exc)}
    return render_template("rifas_publica.html", **dados)


@rifas_public_bp.route("/rifas/comprar", methods=["POST"])
def comprar_rifa():
    data = request.get_json(silent=True) or request.form

    try:
        quantidade = int(data.get("quantidade_rifas", 0))

        resultado = purchase_rifas(
            nome=data.get("nome", ""),
            telefone=data.get("telefone", ""),
            endereco=data.get("endereco", ""),
            email=data.get("email", ""),
            quantidade_rifas=quantidade,
        )

        from extensions import db
        db.session.commit()  # ✅ ESSENCIAL

        return jsonify(resultado.asdict()), 201

    except ValueError:
        from extensions import db
        db.session.rollback()
        return jsonify({"erro": "Quantidade de rifas invalida."}), 400

    except RifaSchemaMissingError as exc:
        from extensions import db
        db.session.rollback()
        return jsonify({"erro": str(exc)}), 503

    except RifaError as exc:
        from extensions import db
        db.session.rollback()
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


@rifas_public_bp.route("/rifas/pagamento/<payment_id>/comprovante", methods=["POST"])
def pagamento_comprovante_publico(payment_id):
    try:
        pagamento = save_receipt(pagamento_id=payment_id, arquivo=request.files.get("comprovante"))
        return jsonify({
            "status": "ok",
            "pagamento_id": pagamento.id,
            "comprovante_path": pagamento.comprovante_path,
        })
    except RifaSchemaMissingError as exc:
        return jsonify({"erro": str(exc)}), 503
    except RifaError as exc:
        return jsonify({"erro": str(exc)}), 400


@rifas_public_bp.route("/rifas/pagamento/<payment_id>/pdf", methods=["GET"])
def pagamento_pdf_publico(payment_id):
    try:
        pagamento = get_payment(payment_id)
    except RifaSchemaMissingError as exc:
        return jsonify({"erro": str(exc)}), 503
    if pagamento is None or not pagamento.pdf_path:
        return jsonify({"erro": "PDF ainda nao disponivel."}), 404
    return send_file(Path(pagamento.pdf_path), mimetype="application/pdf", download_name=f"rifas-{payment_id}.pdf", as_attachment=False)


@rifas_public_bp.route("/rifas/webhook/pix", methods=["POST"])
@rifas_public_bp.route("/webhook/pix", methods=["POST"])
def webhook_pix():
    payload = request.get_json(silent=True) or {}
    raw_body = request.get_data() or b""
    assinatura = request.headers.get("X-Webhook-Signature", "")
    try:
        from extensions import db
        pagamento = process_webhook(payload, raw_body, assinatura)
        db.session.commit()
        return jsonify({"status": "ok", "pagamento_id": pagamento.id})
    except RifaSchemaMissingError as exc:
        from extensions import db
        db.session.rollback()
        return jsonify({"erro": str(exc)}), 503
    except RifaError as exc:
        from extensions import db
        db.session.rollback()
        return jsonify({"erro": str(exc)}), 400
