from pathlib import Path
from urllib.parse import quote
from flask import Blueprint, jsonify, render_template, request, send_file, session
from models import PagamentoRifa, ClienteRifa
from rifas.services import cancelar_pagamentos_expirados
from datetime import datetime, timedelta
from rifas.services import (
    RifaError,
    RifaSchemaMissingError,
    generate_vendor_link,
    get_payment,
    get_public_page_data,
    get_vendedor_by_codigo,
    payment_summary,
    process_webhook,
    purchase_rifas,
    save_receipt,
)


rifas_public_bp = Blueprint("rifas_public", __name__)


@rifas_public_bp.route("/rifas", methods=["GET"])
@rifas_public_bp.route("/acao_entre_fieis", methods=["GET"])
def rifas_home():
    #cancelar_pagamentos_expirados()  # 👈 AQUI

    try:
        dados = get_public_page_data()
    except RifaSchemaMissingError as exc:
        dados = {"campanha": None, "disponiveis": 0, "vendidos": 0, "schema_message": str(exc)}
    dados["mostrar_vendidos"] = False  # 👈 AQUI
    dados["mostrar_data_sorteio"] = False  # 👈 NOVO
    dados["mostrar_vendedor"] = False

    # Mantem o vendedor da landing page vinculado ao restante da jornada.
    ref = (request.args.get("ref") or "").strip().upper()
    if ref:
        session["rifa_ref_vendedor"] = ref

    vendedor_ref = session.get("rifa_ref_vendedor")
    vendedor_obj = None
    if vendedor_ref and not dados.get("schema_message"):
        vendedor_obj = get_vendedor_by_codigo(vendedor_ref)
    if vendedor_ref and vendedor_obj is None:
        session.pop("rifa_ref_vendedor", None)
        vendedor_ref = None

    dados["vendedor_ref"] = vendedor_ref
    dados["vendedor_nome"] = vendedor_obj.nome if vendedor_obj else None
    dados["vendedor_link"] = generate_vendor_link(vendedor_ref) if vendedor_ref else None
    
    mensagem = "Olá, quero informações sobre a rifa"

    if dados.get("campanha"):
        mensagem = f"Olá, quero saber mais sobre a rifa {dados['campanha'].titulo}"

    dados["whatsapp_link"] = f"https://wa.me/556332148559?text={quote(mensagem)}"    
    
    return render_template("rifas_publica.html", **dados)


@rifas_public_bp.route("/rifas/comprar", methods=["POST"])
def comprar_rifa():
    data = request.get_json(silent=True) or request.form

    from extensions import db

    try:
        quantidade = int(data.get("quantidade_rifas", 0))
        telefone = data.get("telefone", "")

        # 🔒 ANTI DUPLICIDADE (MESMO TELEFONE + PENDENTE)
        

        limite = datetime.utcnow() - timedelta(minutes=10)

        pagamento_existente = db.session.execute(
            db.select(PagamentoRifa)
            .join(ClienteRifa)
            .where(
                ClienteRifa.telefone == telefone,
                PagamentoRifa.status == "pendente",
                PagamentoRifa.created_at > limite
            )
        ).scalar_one_or_none()

        if pagamento_existente:
            return jsonify({
                "erro": "Você já possui um pagamento pendente. Finalize antes de gerar outro."
            }), 400

        resultado = purchase_rifas(
            nome=data.get("nome", ""),
            telefone=telefone,
            endereco=data.get("endereco", ""),
            email = data.get("email") or None,
            vendedor=session.get("rifa_ref_vendedor") or data.get("vendedor", ""),
            quantidade_rifas=quantidade,
        )

        db.session.commit()

        return jsonify(resultado.asdict()), 201

    except ValueError:
        db.session.rollback()
        return jsonify({"erro": "Quantidade de rifas invalida."}), 400

    except RifaSchemaMissingError as exc:
        db.session.rollback()
        return jsonify({"erro": str(exc)}), 503

    except RifaError as exc:
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
        pagamento = get_payment(payment_id)

        # 🔒 VALIDAÇÕES AQUI 👇
        if not pagamento:
            return jsonify({"erro": "Pagamento não encontrado"}), 404

        if pagamento.status == "cancelado":
            return jsonify({"erro": "Pedido expirado. Gere um novo."}), 400

        if pagamento.status == "pago":
            return jsonify({"erro": "Pagamento já confirmado."}), 400

        if pagamento.status == "comprovante":
            return jsonify({"erro": "Comprovante já enviado."}), 400

        # ✅ SÓ PASSA SE FOR PENDENTE
        pagamento = save_receipt(
            pagamento_id=payment_id,
            arquivo=request.files.get("comprovante")
        )

        return jsonify({
            "status": "ok",
            "pagamento_id": pagamento.id,
            "comprovante_path": pagamento.comprovante_path,
        })

    except RifaSchemaMissingError as exc:
        return jsonify({"erro": str(exc)}), 503

    except RifaError as exc:
        return jsonify({"erro": str(exc)}), 400
        

from pathlib import Path

@rifas_public_bp.route("/rifas/pagamento/<payment_id>/pdf", methods=["GET"])
def pagamento_pdf_publico(payment_id):
    try:
        pagamento = get_payment(payment_id)
    except RifaSchemaMissingError as exc:
        return jsonify({"erro": str(exc)}), 503

    if pagamento is None:
        return jsonify({"erro": "Pagamento não encontrado."}), 404

    if not pagamento.pdf_path:
        return jsonify({"erro": "PDF ainda nao disponivel."}), 404

    pdf_path = Path(pagamento.pdf_path)

    # 🔥 se não existir → tenta gerar novamente
    if not pdf_path.exists():
        try:
            from rifas.pdf_generator import generate_tickets_pdf

            novo_pdf = generate_tickets_pdf(
                pagamento=pagamento,
                rifas=sorted(pagamento.rifas, key=lambda r: r.numero),
                cliente=pagamento.cliente,
            )

            pdf_path = Path(novo_pdf)

        except Exception as e:
            return jsonify({"erro": f"Erro ao gerar PDF: {str(e)}"}), 500

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=False
    )


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

@rifas_public_bp.route("/rifas/consultar", methods=["POST"])
def consultar_pedido():
    data = request.get_json(silent=True) or request.form

    pedido_id = (data.get("pedido_id") or "").strip()
    telefone = (data.get("telefone") or "").strip()

    from extensions import db

    # 🔎 CONSULTA POR PEDIDO (mantém igual)
    if pedido_id:
        pagamento = get_payment(pedido_id)
        if not pagamento:
            return jsonify({"erro": "Pedido não encontrado"}), 404
        return jsonify({"pedidos": [payment_summary(pagamento)]})

    # 🔎 CONSULTA POR TELEFONE (AGORA LISTA TODOS)
    if telefone:
        telefone_limpo = ''.join(filter(str.isdigit, telefone))

        pagamentos = db.session.execute(
            db.select(PagamentoRifa)
            .join(ClienteRifa)
            .where(ClienteRifa.telefone == telefone_limpo)
            .order_by(PagamentoRifa.created_at.desc())
        ).scalars().all()

        if not pagamentos:
            return jsonify({"erro": "Nenhum pedido encontrado para este telefone"}), 404

        return jsonify({
            "pedidos": [payment_summary(p) for p in pagamentos]
        })

    return jsonify({"erro": "Informe o pedido ou telefone"}), 400
