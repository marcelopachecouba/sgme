from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from models import Escala, Missa
from services.firebase_service import enviar_push
from services.dashboard_service import construir_dashboard
from utils.auth import admin_required


dashboard_bp = Blueprint("dashboard", __name__)


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
    missa = Missa.query.filter_by(
        id=missa_id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()

    escalas = Escala.query.filter_by(
        id_missa=missa.id,
        id_paroquia=current_user.id_paroquia
    ).all()

    enviados = 0
    sem_token = 0

    for escala in escalas:
        ministro = escala.ministro
        if not ministro or not ministro.firebase_token:
            sem_token += 1
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

    flash(
        f"Aviso enviado via Firebase para {enviados} ministro(s). "
        f"{sem_token} sem token ativo."
    )
    return redirect(url_for("dashboard.home"))
