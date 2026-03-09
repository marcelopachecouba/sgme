from flask import Blueprint, render_template, request
from flask_login import login_required
from models import Ministro, Missa, Aviso

busca_bp = Blueprint("busca", __name__)

@busca_bp.route("/busca")
@login_required
def busca():

    termo = request.args.get("q", "")

    ministros = Ministro.query.filter(
        Ministro.nome.ilike(f"%{termo}%")
    ).all()

    missas = Missa.query.filter(
        Missa.comunidade.ilike(f"%{termo}%")
    ).all()

    avisos = Aviso.query.filter(
        Aviso.titulo.ilike(f"%{termo}%")
    ).all()

    return render_template(
        "busca.html",
        termo=termo,
        ministros=ministros,
        missas=missas,
        avisos=avisos
    )