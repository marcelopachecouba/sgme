from datetime import date, timedelta
import urllib.parse

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from models import Escala, Missa
from services.firebase_service import enviar_push
from services.dashboard_service import construir_dashboard
from utils.auth import admin_required


dashboard_bp = Blueprint("dashboard", __name__)



def _escala_missa_da_paroquia(missa_id):
    missa = Missa.query.filter_by(
        id=missa_id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()
    escalas = Escala.query.filter_by(
        id_missa=missa.id,
        id_paroquia=current_user.id_paroquia
    ).all()
    return missa, escalas


@dashboard_bp.route("/")
@login_required
def home():
    hoje = date.today()
    dados = construir_dashboard(
        id_paroquia=current_user.id_paroquia,
        inicio=hoje,
        fim=hoje + timedelta(days=7),
    )
    return render_template("dashboard.html", **dados)


@dashboard_bp.route("/dashboard/avisar_missa/<int:missa_id>", methods=["POST"])
@login_required
@admin_required
def avisar_missa(missa_id):
    missa, escalas = _escala_missa_da_paroquia(missa_id)

    enviados = 0
    sem_token = 0
    nomes_enviados = []
    nomes_sem_token = []

    for escala in escalas:
        ministro = escala.ministro
        if not ministro or not ministro.firebase_token:
            sem_token += 1
            if ministro:
                nomes_sem_token.append(ministro.nome)
            continue

        enviar_push(
            ministro.firebase_token,
            "Lembrete de Escala",
            (
                f"Voce esta escalado para {missa.data.strftime('%d/%m/%Y')} "
                f"as {missa.horario} na comunidade {missa.comunidade}."
            )
        )
        enviados += 1
        nomes_enviados.append(ministro.nome)

    resumo = f"Aviso enviado via Firebase para {enviados} ministro(s). {sem_token} sem token ativo."
    flash(resumo)

    if nomes_enviados:
        flash("Receberam push: " + ", ".join(nomes_enviados))
    if nomes_sem_token:
        flash("Sem token ativo: " + ", ".join(nomes_sem_token))

    return redirect(url_for("dashboard.home"))


@dashboard_bp.route("/dashboard/sem_token/<int:missa_id>")
@login_required
@admin_required
def sem_token_missa(missa_id):
    missa, escalas = _escala_missa_da_paroquia(missa_id)

    sem_token = []
    ids = set()
    for escala in escalas:
        ministro = escala.ministro
        if not ministro or ministro.id in ids:
            continue
        ids.add(ministro.id)
        if not ministro.firebase_token:
            link_wpp = None
            if ministro.telefone:
                mensagem = (
                    f"Ola {ministro.nome},\n\n"
                    "Ative as notificacoes no app/site para receber avisos de escala.\n"
                    f"Voce esta escalado para {missa.data.strftime('%d/%m/%Y')} as {missa.horario} "
                    f"na comunidade {missa.comunidade}.\n\n"
                    "Abra o sistema e permita notificacoes no navegador."
                )
                link_wpp = f"https://wa.me/55{ministro.telefone}?text={urllib.parse.quote(mensagem)}"

            sem_token.append({
                "nome": ministro.nome,
                "telefone": ministro.telefone,
                "link_wpp": link_wpp,
            })

    return render_template(
        "dashboard_sem_token.html",
        missa=missa,
        ministros=sem_token
    )


@dashboard_bp.route("/dashboard/whatsapp_sem_token/<int:missa_id>")
@login_required
@admin_required
def whatsapp_sem_token_missa(missa_id):
    missa, escalas = _escala_missa_da_paroquia(missa_id)

    links = []
    ids = set()
    for escala in escalas:
        ministro = escala.ministro
        if not ministro or ministro.id in ids:
            continue
        ids.add(ministro.id)

        if not ministro.telefone:
            continue

        mensagem = (
            f"Ola {ministro.nome},\n\n"
            "Ative as notificacoes no app/site para receber avisos de escala.\n"
            f"Voce esta escalado para {missa.data.strftime('%d/%m/%Y')} as {missa.horario} "
            f"na comunidade {missa.comunidade}.\n\n"
            "Abra o sistema e permita notificacoes no navegador."
        )
        links.append({
            "nome": ministro.nome,
            "link": f"https://wa.me/55{ministro.telefone}?text={urllib.parse.quote(mensagem)}"
        })

    if not links:
        flash("Nenhum ministro com telefone cadastrado para esta missa.")
        return redirect(url_for("dashboard.home"))

    return render_template("whatsapp_lista.html", links=links)
