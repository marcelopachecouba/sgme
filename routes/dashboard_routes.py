from flask import Blueprint, render_template, redirect, request, url_for, flash, send_file
from flask_login import login_required, current_user, login_user, logout_user
from models import db, Paroquia, Ministro, Missa, Escala, Indisponibilidade, EscalaFixa
from datetime import datetime, date, timedelta
import calendar, uuid, urllib.parse, base64, io
from utils.auth import admin_required
from sqlalchemy.orm import joinedload

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
@login_required
def home():

    hoje = date.today()
    inicio_semana = hoje
    fim_semana = hoje + timedelta(days=7)

    # Missas dos próximos 7 dias
    proximas_missas = Missa.query.filter(
        Missa.id_paroquia == current_user.id_paroquia,
        Missa.data >= inicio_semana,
        Missa.data <= fim_semana
    ).order_by(Missa.data, Missa.horario).all()

    estrutura_missas = []

    for missa in proximas_missas:

        escalas = Escala.query.options(
            joinedload(Escala.ministro)
        ).filter_by(id_missa=missa.id).all()

        ministros = []
        telefones = []

        for e in escalas:
            if e.ministro:
                ministros.append(e.ministro.nome)

                if e.ministro.telefone:
                    telefones.append(f"55{e.ministro.telefone}")

        mensagem = f"""
Lembrete de Escala - Ministério da Eucaristia

Data: {missa.data.strftime('%d/%m/%Y')}
Horário: {missa.horario}
Comunidade: {missa.comunidade}

Deus abençoe seu ministério.
"""

        mensagem = urllib.parse.quote(mensagem)

        # link whatsapp grupo
        link_whatsapp = None

        if telefones:
            numeros = ",".join(telefones)
            link_whatsapp = f"https://wa.me/{telefones[0]}?text={mensagem}"

        estrutura_missas.append({
            "missa": missa,
            "ministros": ministros,
            "whatsapp": link_whatsapp
        })

    return render_template(
        "dashboard.html",
        proximas_missas=estrutura_missas
    )
# ======================
# MINISTROS
# ======================


