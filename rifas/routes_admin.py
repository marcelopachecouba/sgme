from flask import Blueprint, jsonify, render_template
from flask_login import login_required

from utils.auth import admin_required
from rifas.services import RifaSchemaMissingError, admin_dashboard_data


rifas_admin_bp = Blueprint("rifas_admin", __name__)


def _dados_fallback(mensagem: str) -> dict:
    return {
        "pagamentos": [],
        "clientes": [],
        "rifas": [],
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


@rifas_admin_bp.route("/admin/rifas", methods=["GET"])
@login_required
@admin_required
def admin_rifas():
    try:
        dados = admin_dashboard_data()
    except RifaSchemaMissingError as exc:
        dados = _dados_fallback(str(exc))
    return render_template("admin_rifas.html", **dados)


@rifas_admin_bp.route("/admin/pagamentos", methods=["GET"])
@login_required
@admin_required
def admin_pagamentos():
    try:
        dados = admin_dashboard_data()
    except RifaSchemaMissingError as exc:
        dados = _dados_fallback(str(exc))
    return render_template("admin_pagamentos_rifas.html", **dados)


@rifas_admin_bp.route("/admin/clientes", methods=["GET"])
@login_required
@admin_required
def admin_clientes():
    try:
        dados = admin_dashboard_data()
    except RifaSchemaMissingError as exc:
        dados = _dados_fallback(str(exc))
    return render_template("admin_clientes_rifas.html", **dados)


@rifas_admin_bp.route("/admin/relatorio", methods=["GET"])
@login_required
@admin_required
def admin_relatorio():
    try:
        dados = admin_dashboard_data()
    except RifaSchemaMissingError as exc:
        dados = _dados_fallback(str(exc))
    return render_template("admin_relatorio_rifas.html", **dados)


@rifas_admin_bp.route("/admin/rifas/resumo.json", methods=["GET"])
@login_required
@admin_required
def admin_rifas_resumo():
    try:
        dados = admin_dashboard_data()
        return jsonify(dados["stats"])
    except RifaSchemaMissingError as exc:
        return jsonify({"erro": str(exc)}), 503
