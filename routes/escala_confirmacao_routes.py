from flask import Blueprint, render_template
from models import Escala

confirmacao_bp = Blueprint("confirmacao", __name__)


@confirmacao_bp.route("/escala/<token>")
def escala_confirmacao(token):

    escala = Escala.query.filter_by(token=token).first_or_404()

    return render_template(
        "escala_confirmacao.html",
        escala=escala
    )