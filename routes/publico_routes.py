from flask import Blueprint, render_template, redirect, request, url_for, flash, send_file
from flask_login import login_required, current_user, login_user, logout_user
from models import db, Paroquia, Ministro, Missa, Escala, Indisponibilidade, EscalaFixa
from datetime import datetime, date, timedelta
import calendar, uuid, urllib.parse, base64, io
from utils.auth import admin_required
from services.public_url_service import build_public_url
import qrcode
from io import BytesIO

publico_bp = Blueprint("publico", __name__)

@publico_bp.route("/ministro/<token>")
def ministro_publico(token):

    ministro = Ministro.query.filter_by(token_publico=token).first_or_404()

    escalas = Escala.query.join(Missa).filter(
        Escala.id_ministro == ministro.id,
        Escala.id_paroquia == ministro.id_paroquia,
        Missa.id_paroquia == ministro.id_paroquia,
    ).order_by(Missa.data).all()

    return render_template(
        "ministro_publico.html",
        ministro=ministro,
        escalas=escalas
    )


@publico_bp.route("/calendario/publico/<token>")
def calendario_publico(token):

    ministro = Ministro.query.filter_by(token_publico=token).first_or_404()

    hoje = date.today()
    mes = int(request.args.get("mes", hoje.month))
    ano = int(request.args.get("ano", hoje.year))

    cal = calendar.monthcalendar(ano, mes)

    missas = Missa.query.filter(
        Missa.id_paroquia == ministro.id_paroquia,
        db.extract("month", Missa.data) == mes,
        db.extract("year", Missa.data) == ano
    ).all()

    estrutura = {}

    for missa in missas:

        dia = missa.data.day

        if dia not in estrutura:
            estrutura[dia] = []

        escalas = Escala.query.filter_by(
            id_missa=missa.id,
            id_paroquia=ministro.id_paroquia
        ).all()

        ministros = []
        for e in escalas:
            if e.ministro:
                ministros.append({
                    "nome": e.ministro.nome,
                    "eh_ele": e.ministro.id == ministro.id
                })

        estrutura[dia].append({
            "horario": missa.horario,
            "comunidade": missa.comunidade,
            "ministros": ministros
        })

    return render_template(
        "calendario_publico.html",
        cal=cal,
        estrutura=estrutura,
        mes=mes,
        ano=ano,
        ministro=ministro
    )


@publico_bp.route("/ministro/qrcode/<token>")
def qr_ministro(token):

    ministro = Ministro.query.filter_by(token_publico=token).first_or_404()

    link = build_public_url(
        "publico.calendario_publico",
        token=ministro.token_publico,
    )

    qr = qrcode.make(link)

    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)

    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    return render_template(
        "qr_ministro.html",
        ministro=ministro,
        qr_code=img_base64
    )


@publico_bp.route("/paroquia/<int:id>")
@publico_bp.route("/escalas/publicas/<int:id>")
def calendario_paroquia(id):

    paroquia = Paroquia.query.get_or_404(id)

    hoje = date.today()
    try:
        mes = int(request.args.get("mes", hoje.month))
    except (TypeError, ValueError):
        mes = hoje.month
    try:
        ano = int(request.args.get("ano", hoje.year))
    except (TypeError, ValueError):
        ano = hoje.year

    if mes < 1 or mes > 12:
        mes = hoje.month

    cal = calendar.monthcalendar(ano, mes)

    missas = Missa.query.filter(
        Missa.id_paroquia == id,
        db.extract("month", Missa.data) == mes,
        db.extract("year", Missa.data) == ano
    ).order_by(Missa.data.asc(), Missa.horario.asc(), Missa.id.asc()).all()

    estrutura = {}

    for missa in missas:
        dia = missa.data.day

        if dia not in estrutura:
            estrutura[dia] = []

        escalas = Escala.query.filter_by(
            id_missa=missa.id,
            id_paroquia=id
        ).all()

        nomes = []
        for e in escalas:
            if e.ministro:
                nomes.append(e.ministro.nome)

        estrutura[dia].append({
            "horario": missa.horario,
            "comunidade": missa.comunidade,
            "ministros": nomes
        })

    link_publico = build_public_url(
        "publico.calendario_paroquia",
        id=paroquia.id,
        mes=mes,
        ano=ano,
    )

    return render_template(
        "calendario_paroquia.html",
        cal=cal,
        estrutura=estrutura,
        paroquia=paroquia,
        mes=mes,
        ano=ano,
        link_publico=link_publico,
    )
