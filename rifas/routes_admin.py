from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, redirect, render_template, request, send_file, url_for, flash
from flask_login import login_required

from utils.auth import admin_required
from extensions import db  # ✅ ADICIONADO

from rifas.services import (
    RifaError,
    RifaSchemaMissingError,
    admin_dashboard_data,
    confirm_payment,
    create_or_update_campaign,
    get_campaign,
    payment_detail_data,
)


rifas_admin_bp = Blueprint("rifas_admin", __name__)


def _dados_fallback(mensagem: str) -> dict:
    return {
        "pagamentos": [],
        "clientes": [],
        "rifas": [],
        "campanhas": [],
        "campanha_ativa": None,
        "ranking_compradores": [],
        "stats": {
            "total_pago": 0,
            "disponiveis": 0,
            "reservadas": 0,
            "pagas": 0,
            "clientes": 0,
            "pagamentos": 0,
        },
        "schema_message": mensagem,
    }


def _base_context():
    try:
        return admin_dashboard_data()
    except RifaSchemaMissingError as exc:
        return _dados_fallback(str(exc))


def _parse_date(value: str):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


@rifas_admin_bp.route("/admin/rifas", methods=["GET"])
@login_required
@admin_required
def admin_rifas():
    dados = _base_context()
    return render_template("admin_rifas.html", **dados)


@rifas_admin_bp.route("/admin/pagamentos", methods=["GET"])
@login_required
@admin_required
def admin_pagamentos():
    dados = _base_context()
    return render_template("admin_pagamentos_rifas.html", **dados)


@rifas_admin_bp.route("/admin/pagamentos/<payment_id>", methods=["GET"])
@login_required
@admin_required
def admin_pagamento_detalhe(payment_id):
    dados = _base_context()
    try:
        detalhe = payment_detail_data(payment_id)
        dados.update(detalhe)
    except RifaError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("rifas_admin.admin_pagamentos"))
    return render_template("admin_pagamento_rifa_detalhe.html", **dados)


# ✅ CORRIGIDO
@rifas_admin_bp.route("/admin/pagamentos/<payment_id>/aprovar", methods=["POST"])
@login_required
@admin_required
def admin_pagamento_aprovar(payment_id):
    observacoes = (request.form.get("observacoes_admin") or "").strip()

    try:
        confirm_payment(pagamento_id=payment_id, observacoes_admin=observacoes)

        db.session.commit()  # ✅ ESSENCIAL

        flash("Pagamento marcado como pago com sucesso.", "success")

    except RifaError as exc:
        db.session.rollback()  # ✅ ESSENCIAL
        flash(str(exc), "danger")

    return redirect(url_for("rifas_admin.admin_pagamento_detalhe", payment_id=payment_id))


@rifas_admin_bp.route("/admin/pagamentos/<payment_id>/pdf", methods=["GET"])
@login_required
@admin_required
def admin_pagamento_pdf(payment_id):
    try:
        detalhe = payment_detail_data(payment_id)
    except RifaError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("rifas_admin.admin_pagamentos"))

    pagamento = detalhe["pagamento"]
    if not pagamento.pdf_path:
        flash("O PDF ainda nao foi gerado para este pagamento.", "warning")
        return redirect(url_for("rifas_admin.admin_pagamento_detalhe", payment_id=payment_id))

    return send_file(
        Path(pagamento.pdf_path),
        mimetype="application/pdf",
        download_name=f"rifas-{payment_id}.pdf",
        as_attachment=False
    )


@rifas_admin_bp.route("/admin/clientes", methods=["GET"])
@login_required
@admin_required
def admin_clientes():
    dados = _base_context()
    return render_template("admin_clientes_rifas.html", **dados)


@rifas_admin_bp.route("/admin/relatorio", methods=["GET"])
@login_required
@admin_required
def admin_relatorio():
    dados = _base_context()
    return render_template("admin_relatorio_rifas.html", **dados)


# ✅ CORRIGIDO
@rifas_admin_bp.route("/admin/rifas/cadastro", methods=["GET", "POST"])
@login_required
@admin_required
def admin_rifas_cadastro():
    campanha = None

    if request.method == "POST":
        campanha_id = (request.form.get("campanha_id") or "").strip() or None
        titulo = request.form.get("titulo", "")
        descricao = request.form.get("descricao", "")
        data_sorteio = _parse_date(request.form.get("data_sorteio", ""))
        ativa = request.form.get("ativa") == "on"

        try:
            quantidade_total = int(request.form.get("quantidade_total", "0"))
            valor_rifa = float((request.form.get("valor_rifa", "0") or "0").replace(",", "."))

            campanha = create_or_update_campaign(
                campanha_id=campanha_id,
                titulo=titulo,
                descricao=descricao,
                data_sorteio=data_sorteio,
                valor_rifa=valor_rifa,
                quantidade_total=quantidade_total,
                ativa=ativa,
            )

            db.session.commit()  # ✅ ESSENCIAL

            flash("Campanha de rifa salva com sucesso.", "success")

            return redirect(url_for("rifas_admin.admin_rifas_cadastro", campanha_id=campanha.id))

        except (ValueError, RifaError) as exc:
            db.session.rollback()  # ✅ ESSENCIAL
            flash(str(exc), "danger")

    dados = _base_context()
    campanha_id = request.args.get("campanha_id")

    if campanha_id:
        campanha = get_campaign(campanha_id)

    dados["campanha_form"] = campanha or dados.get("campanha_ativa")

    return render_template("admin_rifa_cadastro.html", **dados)


@rifas_admin_bp.route("/admin/rifas/resumo.json", methods=["GET"])
@login_required
@admin_required
def admin_rifas_resumo():
    try:
        dados = admin_dashboard_data()
        return jsonify(dados["stats"])
    except RifaSchemaMissingError as exc:
        return jsonify({"erro": str(exc)}), 503