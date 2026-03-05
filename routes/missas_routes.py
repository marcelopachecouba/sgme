from flask import Blueprint, render_template, redirect, request, url_for, flash, send_file
from flask_login import login_required, current_user, login_user, logout_user
from models import db, Paroquia, Ministro, Missa, Escala, Indisponibilidade, EscalaFixa
from datetime import datetime, date, timedelta
import calendar, uuid, urllib.parse, base64, io
from utils.auth import admin_required

missas_bp = Blueprint("missas", __name__)

@missas_bp.route("/missas")
@login_required
def missas():
    lista = Missa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).all()
    return render_template("missas.html", missas=lista)


@missas_bp.route("/missas/calendario")
@login_required
def calendario_missas():

    hoje = date.today()

    mes = int(request.args.get("mes", hoje.month))
    ano = int(request.args.get("ano", hoje.year))

    cal = calendar.monthcalendar(ano, mes)

    missas = Missa.query.filter(
        Missa.id_paroquia == current_user.id_paroquia,
        db.extract("month", Missa.data) == mes,
        db.extract("year", Missa.data) == ano
    ).all()

    estrutura = {}

    for missa in missas:

        dia = missa.data.day

        if dia not in estrutura:
            estrutura[dia] = []

        escalas = Escala.query.filter_by(id_missa=missa.id).all()
        
        ministros = []

        for e in escalas:
            if e.ministro:
               ministros.append(e.ministro.nome)

        estrutura[dia].append({
            "horario": missa.horario,
            "comunidade": missa.comunidade,
            "ministros": ministros
        })

    return render_template(
        "calendario_missas.html",
        cal=cal,
        estrutura=estrutura,
        mes=mes,
        ano=ano
    )

from utils.auth import admin_required
@missas_bp.route("/missas/nova", methods=["GET", "POST"])
@login_required
@admin_required
def nova_missa():
    if request.method == "POST":
        data = datetime.strptime(request.form["data"], "%Y-%m-%d")
        horario = request.form["horario"]
        comunidade = request.form["comunidade"]
        qtd = request.form["qtd"]

        missa = Missa(
            data=data,
            horario=horario,
            comunidade=comunidade,
            qtd_ministros=qtd,
            id_paroquia=current_user.id_paroquia
        )

        db.session.add(missa)
        db.session.commit()
        return redirect(url_for("missas.missas"))

    return render_template("nova_missa.html")


from utils.auth import admin_required
@missas_bp.route("/missas/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required

def editar_missa(id):

    missa = Missa.query.get_or_404(id)

    if request.method == "POST":

        missa.data = datetime.strptime(request.form["data"], "%Y-%m-%d")
        missa.horario = request.form["horario"]
        missa.comunidade = request.form["comunidade"]
        missa.qtd_ministros = int(request.form["qtd"])

        db.session.commit()

        flash("Missa atualizada com sucesso!")
        return redirect(url_for("missas.missas"))

    return render_template("editar_missa.html", missa=missa)

from utils.auth import admin_required
@missas_bp.route("/missas/excluir/<int:id>")
@login_required
@admin_required
def excluir_missa(id):

    missa = Missa.query.get_or_404(id)

    # Remove escalas vinculadas primeiro
    Escala.query.filter_by(id_missa=missa.id).delete()

    db.session.delete(missa)
    db.session.commit()

    flash("Missa excluída com sucesso!")
    return redirect(url_for("missas.missas"))



@missas_bp.route("/missas/visao")
@login_required
def visao_missas():

    missas = Missa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Missa.data, Missa.horario).all()

    estrutura = {}

    for missa in missas:

        data = missa.data
        semana = (data.day - 1) // 7 + 1
        dia_semana = data.weekday()  # 0=segunda
        horario = missa.horario

        if semana not in estrutura:
            estrutura[semana] = {}

        if dia_semana not in estrutura[semana]:
            estrutura[semana][dia_semana] = {}

        if horario not in estrutura[semana][dia_semana]:
            estrutura[semana][dia_semana][horario] = []

        estrutura[semana][dia_semana][horario].append(missa)

    return render_template(
        "visao_missas.html",
        estrutura=estrutura
    )

# ======================
# ESCALA MANUAL
# ======================


