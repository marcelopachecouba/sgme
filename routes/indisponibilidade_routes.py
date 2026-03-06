from flask import Blueprint, render_template, request, redirect, url_for, abort, flash
from flask_login import login_required, current_user
from models import db, Ministro, IndisponibilidadeFixa
import re

indisp_bp = Blueprint("indisponibilidade", __name__)


@indisp_bp.route("/indisponibilidade")
@login_required
def listar_indisponibilidade():

    regras = IndisponibilidadeFixa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(
        IndisponibilidadeFixa.semana.asc(),
        IndisponibilidadeFixa.dia_semana.asc(),
        IndisponibilidadeFixa.horario.asc()
    ).all()

    return render_template(
        "indisponibilidade.html",
        regras=regras
    )


@indisp_bp.route("/indisponibilidade/nova", methods=["GET", "POST"])
@login_required
def nova_indisponibilidade():

    ministros = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Ministro.nome.asc()).all()

    if request.method == "POST":

        ministro_id = request.form["ministro"]
        ministro = Ministro.query.filter_by(
            id=ministro_id,
            id_paroquia=current_user.id_paroquia
        ).first()
        if not ministro:
            abort(403)
        semana = request.form.get("semana")
        dia_semana = request.form["dia_semana"]
        horario = (request.form.get("horario") or "").strip()

        if horario and not re.match(r"^\d{2}:\d{2}$", horario):
            flash("Horario invalido. Use o formato HH:MM.")
            return redirect(url_for("indisponibilidade.nova_indisponibilidade"))

        regra = IndisponibilidadeFixa(
            id_ministro=ministro_id,
            id_paroquia=current_user.id_paroquia,
            semana=int(semana) if semana else None,
            dia_semana=int(dia_semana),
            horario=horario if horario else None
        )

        db.session.add(regra)
        db.session.commit()
        flash("Indisponibilidade cadastrada com sucesso.")

        return redirect(url_for("indisponibilidade.listar_indisponibilidade"))

    return render_template(
        "nova_indisponibilidade.html",
        ministros=ministros
    )


@indisp_bp.route("/indisponibilidade/excluir/<int:id>", methods=["POST"])
@login_required
def excluir_indisponibilidade(id):

    regra = IndisponibilidadeFixa.query.get_or_404(id)
    if regra.id_paroquia != current_user.id_paroquia:
        abort(403)

    db.session.delete(regra)
    db.session.commit()
    flash("Indisponibilidade removida.")

    return redirect(url_for("indisponibilidade.listar_indisponibilidade"))
