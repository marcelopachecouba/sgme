from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import Notificacao

notificacao_bp = Blueprint("notificacoes", __name__)


@notificacao_bp.route("/notificacoes")
@login_required
def listar():

    notificacoes = Notificacao.query.filter_by(
        usuario_id=current_user.id
    ).order_by(Notificacao.criada_em.desc()).all()

    return render_template(
        "notificacoes.html",
        notificacoes=notificacoes
    )