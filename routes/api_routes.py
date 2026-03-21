from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from models import Escala, Missa
from utils.auth import admin_required
from services.whatsapp_service import enviar_lembretes_whatsapp

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/minhas_escalas")
@login_required
def minhas_escalas():

    escalas = Escala.query.join(Missa).filter(
        Escala.id_ministro == current_user.id,
        Escala.id_paroquia == current_user.id_paroquia,
        Missa.id_paroquia == current_user.id_paroquia,
    ).order_by(Missa.data).all()

    dados = []

    for e in escalas:

        dados.append({
            "data": e.missa.data.strftime("%d/%m/%Y"),
            "horario": e.missa.horario,
            "comunidade": e.missa.comunidade
        })

    return jsonify(dados)


@api_bp.route("/api/whatsapp/lembretes/enviar-agora", methods=["POST"])
@login_required
@admin_required
def enviar_lembretes_whatsapp_agora():
    json_body = request.get_json(silent=True) or {}
    data_ref = request.form.get("data") or json_body.get("data")
    valor_forcar = request.form.get("forcar") or request.args.get("forcar") or json_body.get("forcar") or ""
    forcar_envio = str(valor_forcar).strip() in {"1", "true", "True"}

    if data_ref:
        try:
            data_alvo = datetime.strptime(data_ref, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"erro": "Data invalida. Use o formato YYYY-MM-DD."}), 400
    else:
        data_alvo = None

    resultado = enviar_lembretes_whatsapp(
        data_alvo=data_alvo,
        id_paroquia=current_user.id_paroquia,
        forcar_envio=forcar_envio,
    )

    return jsonify(resultado)
