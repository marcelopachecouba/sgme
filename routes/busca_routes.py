from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from sqlalchemy import or_

from models import Ministro, Missa, Aviso, db

busca_bp = Blueprint("busca", __name__)


# BUSCA NORMAL
@busca_bp.route("/busca")
@login_required
def busca():

    termo = (request.args.get("q") or "").strip()

    ministros = []
    missas = []
    avisos = []

    if termo:

        ministros = Ministro.query.filter(
            Ministro.nome.ilike(f"%{termo}%")
        ).order_by(Ministro.nome.asc()).all()

        missas = Missa.query.filter(
            or_(
                Missa.comunidade.ilike(f"%{termo}%"),
                Missa.horario.ilike(f"%{termo}%"),
                Missa.data.cast(db.String).ilike(f"%{termo}%")
            )
        ).order_by(Missa.data.desc()).all()

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


# AUTOCOMPLETE
@busca_bp.route("/api/busca")
@login_required
def api_busca():

    termo = (request.args.get("q") or "").strip()

    resultados = []

    if termo:

        ministros = Ministro.query.filter(
            Ministro.nome.ilike(f"%{termo}%")
        ).limit(5).all()

        for m in ministros:
            resultados.append({
                "tipo": "ministro",
                "texto": m.nome
            })

        missas = Missa.query.filter(
            or_(
                Missa.comunidade.ilike(f"%{termo}%"),
                Missa.horario.ilike(f"%{termo}%")
            )
        ).limit(5).all()

        for missa in missas:
            resultados.append({
                "tipo": "missa",
                "texto": f"{missa.data.strftime('%d/%m')} {missa.horario} {missa.comunidade}"
            })

        avisos = Aviso.query.filter(
            Aviso.titulo.ilike(f"%{termo}%")
        ).limit(5).all()

        for aviso in avisos:
            resultados.append({
                "tipo": "aviso",
                "texto": aviso.titulo
            })

    return jsonify({"resultados": resultados})