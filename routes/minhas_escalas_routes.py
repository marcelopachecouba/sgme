from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import db, Escala, Missa
from datetime import datetime

minhas_escalas_bp = Blueprint("minhas_escalas", __name__)

@minhas_escalas_bp.route("/minhas-escalas")
@login_required
def minhas_escalas():

    hoje = datetime.now()

    escalas = (
        db.session.query(Escala, Missa)
        .join(Missa, Escala.missa_id == Missa.id)
        .filter(Escala.ministro_id == current_user.id)
        .filter(Missa.data >= hoje)
        .order_by(Missa.data.asc())
        .all()
    )

    proxima = None
    contagem = None

    if escalas:

        proxima = escalas[0][1]

        delta = proxima.data - hoje

        dias = delta.days
        horas = int(delta.seconds / 3600)

        contagem = f"{dias} dias e {horas} horas"

    return render_template(
        "minhas_escalas.html",
        escalas=escalas,
        proxima=proxima,
        contagem=contagem
    )