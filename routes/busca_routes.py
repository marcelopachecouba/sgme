from flask import Blueprint, render_template, request, jsonify, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from models import Ministro, Missa, Aviso, Escala, db

busca_bp = Blueprint("busca", __name__)


# BUSCA NORMAL
@busca_bp.route("/busca")
@login_required
def busca():

    termo = (request.args.get("q") or "").strip()

    ministros = []
    missas = []
    avisos = []
    escalas = []

    if termo:

        # MINISTROS
        ministros = Ministro.query.filter(
            Ministro.id_paroquia == current_user.id_paroquia,
            Ministro.nome.ilike(f"%{termo}%")
        ).order_by(Ministro.nome.asc()).all()

        # MISSAS
        missas = Missa.query.filter(
            Missa.id_paroquia == current_user.id_paroquia,
            or_(
                Missa.comunidade.ilike(f"%{termo}%"),
                Missa.horario.ilike(f"%{termo}%"),
                Missa.data.cast(db.String).ilike(f"%{termo}%")
            )
        ).order_by(Missa.data.desc()).all()

        # AVISOS
        avisos = Aviso.query.filter(
            Aviso.titulo.ilike(f"%{termo}%")
        ).order_by(Aviso.id.desc()).all()

        # ESCALAS (missas onde o ministro está escalado)
        escalas = db.session.query(Escala, Ministro, Missa)\
            .join(Ministro, Escala.id_ministro == Ministro.id)\
            .join(Missa, Escala.id_missa == Missa.id)\
            .filter(
                Escala.id_paroquia == current_user.id_paroquia,
                Ministro.id_paroquia == current_user.id_paroquia,
                Missa.id_paroquia == current_user.id_paroquia,
                Ministro.nome.ilike(f"%{termo}%")
            )\
            .order_by(Missa.data.desc())\
            .all()

    return render_template(
        "busca.html",
        termo=termo,
        ministros=ministros,
        missas=missas,
        avisos=avisos,
        escalas=escalas
    )


# AUTOCOMPLETE
@busca_bp.route("/api/busca")
@login_required
def api_busca():

    termo = (request.args.get("q") or "").strip()

    resultados = []

    if termo:

        ministros = Ministro.query.filter(
            Ministro.id_paroquia == current_user.id_paroquia,
            Ministro.nome.ilike(f"%{termo}%")
        ).limit(5).all()

        for m in ministros:
            resultados.append({
                "tipo": "ministro",
                "texto": m.nome,
                "url": url_for("ministros.ministros"),
            })

        missas = Missa.query.filter(
            Missa.id_paroquia == current_user.id_paroquia,
            or_(
                Missa.comunidade.ilike(f"%{termo}%"),
                Missa.horario.ilike(f"%{termo}%")
            )
        ).limit(5).all()

        for missa in missas:
            resultados.append({
                "tipo": "missa",
                "texto": f"{missa.data.strftime('%d/%m')} {missa.horario} {missa.comunidade}",
                "url": url_for("escala.visualizar_escala", missa_id=missa.id),
            })

        avisos = Aviso.query.filter(
            Aviso.titulo.ilike(f"%{termo}%")
        ).limit(5).all()

        for aviso in avisos:
            resultados.append({
                "tipo": "aviso",
                "texto": aviso.titulo,
                "url": url_for("avisos.avisos"),
            })

    return jsonify({"resultados": resultados})
