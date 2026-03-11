from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from models import Escala, Missa

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
