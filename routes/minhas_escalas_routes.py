from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import db, Escala, Missa
from datetime import date

minhas_escalas_bp = Blueprint("minhas_escalas", __name__)


@minhas_escalas_bp.route("/minhas-escalas")
@login_required
def minhas_escalas():

    hoje = date.today()

    escalas = (
        db.session.query(Escala, Missa)
        .join(Missa, Escala.id_missa == Missa.id)
        .filter(Escala.id_ministro == current_user.id)
        .filter(Escala.id_paroquia == current_user.id_paroquia)
        .filter(Missa.id_paroquia == current_user.id_paroquia)
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

        contagem = f"{dias} dias"

    return render_template(
        "minhas_escalas.html",
        escalas=escalas,
        proxima=proxima,
        contagem=contagem
    )
