from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import or_

from models import Ministro, Missa, Aviso, db

busca_bp = Blueprint("busca", __name__)


@busca_bp.route("/busca")
@login_required
def busca():

    termo = (request.args.get("q") or "").strip()

    ministros = []
    missas = []
    avisos = []

    if termo:

        # BUSCA MINISTROS
        ministros = Ministro.query.filter(
            or_(
                Ministro.nome.ilike(f"%{termo}%"),
                Ministro.nome_completo.ilike(f"%{termo}%")
            )
        ).order_by(Ministro.nome.asc()).all()

        # BUSCA MISSAS
        missas = Missa.query.filter(
            or_(
                Missa.comunidade.ilike(f"%{termo}%"),
                Missa.horario.ilike(f"%{termo}%"),
                Missa.data.cast(db.String).ilike(f"%{termo}%")
            )
        ).order_by(Missa.data.desc()).all()

        # BUSCA AVISOS
        avisos = Aviso.query.filter(
            Aviso.titulo.ilike(f"%{termo}%")
        ).order_by(Aviso.id.desc()).all()

    return render_template(
        "busca.html",
        termo=termo,
        ministros=ministros,
        missas=missas,
        avisos=avisos
    )