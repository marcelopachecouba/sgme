from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required
from models import db, Paroquia, Ministro, Missa, Escala
from utils.auth import superadmin_required

superadmin_bp = Blueprint("superadmin", __name__)

@superadmin_bp.route("/superadmin")
@login_required
@superadmin_required
def painel_superadmin():

    paroquias = Paroquia.query.all()

    dados = []

    for p in paroquias:

        ministros = Ministro.query.filter_by(id_paroquia=p.id).count()

        missas = Missa.query.filter_by(id_paroquia=p.id).count()

        escalas = Escala.query.filter_by(id_paroquia=p.id).count()

        dados.append({
            "paroquia": p,
            "ministros": ministros,
            "missas": missas,
            "escalas": escalas
        })

    return render_template(
        "superadmin_dashboard.html",
        dados=dados
    )


@superadmin_bp.route("/superadmin/nova_paroquia", methods=["POST"])
@login_required
@superadmin_required
def nova_paroquia():

    nome = request.form["nome"]
    cidade = request.form["cidade"]
    estado = request.form["estado"]

    nova = Paroquia(
        nome=nome,
        cidade=cidade,
        estado=estado
    )

    db.session.add(nova)
    db.session.commit()

    return redirect(url_for("superadmin.painel_superadmin"))
