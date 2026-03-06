from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from models import CasalMinisterio, Ministro, db
from utils.auth import admin_required


casais_bp = Blueprint("casais", __name__)


@casais_bp.route("/casais")
@login_required
@admin_required
def listar_casais():
    ministros = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Ministro.nome.asc()).all()

    casais = CasalMinisterio.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(CasalMinisterio.id.desc()).all()

    return render_template(
        "casais.html",
        ministros=ministros,
        casais=casais,
    )


@casais_bp.route("/casais/novo", methods=["POST"])
@login_required
@admin_required
def novo_casal():
    ministro_1_id = request.form.get("ministro_1_id", type=int)
    ministro_2_id = request.form.get("ministro_2_id", type=int)
    ativo = bool(request.form.get("ativo"))

    if not ministro_1_id or not ministro_2_id:
        flash("Selecione os dois ministros.")
        return redirect(url_for("casais.listar_casais"))

    if ministro_1_id == ministro_2_id:
        flash("Nao e permitido criar casal com o mesmo ministro.")
        return redirect(url_for("casais.listar_casais"))

    m1 = Ministro.query.filter_by(
        id=ministro_1_id,
        id_paroquia=current_user.id_paroquia
    ).first()
    m2 = Ministro.query.filter_by(
        id=ministro_2_id,
        id_paroquia=current_user.id_paroquia
    ).first()

    if not m1 or not m2:
        flash("Ministros invalidos para esta paroquia.")
        return redirect(url_for("casais.listar_casais"))

    existe = CasalMinisterio.query.filter(
        CasalMinisterio.id_paroquia == current_user.id_paroquia,
        or_(
            (CasalMinisterio.id_ministro_1 == ministro_1_id) & (CasalMinisterio.id_ministro_2 == ministro_2_id),
            (CasalMinisterio.id_ministro_1 == ministro_2_id) & (CasalMinisterio.id_ministro_2 == ministro_1_id),
        )
    ).first()

    if existe:
        existe.ativo = ativo
        db.session.commit()
        flash("Casal ja existia e foi atualizado.")
        return redirect(url_for("casais.listar_casais"))

    casal = CasalMinisterio(
        id_ministro_1=ministro_1_id,
        id_ministro_2=ministro_2_id,
        id_paroquia=current_user.id_paroquia,
        ativo=ativo,
    )
    db.session.add(casal)
    db.session.commit()

    flash("Casal cadastrado com sucesso.")
    return redirect(url_for("casais.listar_casais"))


@casais_bp.route("/casais/excluir/<int:casal_id>", methods=["POST"])
@login_required
@admin_required
def excluir_casal(casal_id):
    casal = CasalMinisterio.query.get_or_404(casal_id)
    if casal.id_paroquia != current_user.id_paroquia:
        return redirect(url_for("casais.listar_casais"))

    db.session.delete(casal)
    db.session.commit()
    flash("Casal removido.")
    return redirect(url_for("casais.listar_casais"))
