
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from models import Escala, Missa
from utils.auth import admin_required
from services.whatsapp_service import enviar_lembretes_whatsapp

from flask import Blueprint

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

import json
import requests
from flask import current_app
from rifas.sicoob_service import get_sicoob_token

@api_bp.route("/teste_pix", methods=["GET", "POST"])
def teste_pix():

    import requests
    import json
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    TZ_BR = ZoneInfo("America/Sao_Paulo")

    if request.method == "GET":

        hoje = datetime.now(TZ_BR).strftime("%Y-%m-%d")

        return f"""
        <form method="POST">

            Data Inicial:<br>
            <input type="date" name="data_inicial" value="{hoje}">

            <br><br>

            Data Final:<br>
            <input type="date" name="data_final" value="{hoje}">

            <br><br>

            <button type="submit">
                Consultar PIX
            </button>

        </form>
        """

    data_inicial = request.form["data_inicial"]
    data_final = request.form["data_final"]

    agora = datetime.now(TZ_BR)

    inicio = f"{data_inicial}T00:00:00-03:00"

    # Se consultar o dia atual, usa o horário atual do Brasil
    if data_final == agora.date().isoformat():

        fim = agora.strftime(
            "%Y-%m-%dT%H:%M:%S-03:00"
        )

    else:

        fim = f"{data_final}T23:59:59-03:00"

    token = get_sicoob_token()

    headers = {
        "Authorization": f"Bearer {token}"
    }

    url = current_app.config["SICREDI_API_URL"] + "/pix"

    params = {
        "inicio": inicio,
        "fim": fim
    }

    print("================================")
    print("UTC..........:", datetime.now(timezone.utc))
    print("Brasil.......:", agora)
    print("Inicio.......:", inicio)
    print("Fim..........:", fim)
    print("Parametros...:", params)
    print("================================")

    r = requests.get(

        url,

        headers=headers,

        params=params,

        cert=(

            current_app.config["SICREDI_CERT_PATH"],

            current_app.config["SICREDI_KEY_PATH"]

        ),

        timeout=30

    )

    print("STATUS:", r.status_code)
    print("URL:", r.url)
    print("RESPOSTA:", r.text)

    try:

        dados = r.json()

    except Exception:

        return (
            "<pre>" +
            r.text +
            "</pre>"
        )

    return "<pre>" + json.dumps(

        dados,

        indent=4,

        ensure_ascii=False

    ) + "</pre>"