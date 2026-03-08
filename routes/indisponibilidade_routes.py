import re
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from utils.auth import admin_required

from models import (
    Disponibilidade,
    DisponibilidadeFixa,
    Indisponibilidade,
    IndisponibilidadeFixa,
    Ministro,
    db,
)

indisp_bp = Blueprint("indisponibilidade", __name__)


def _semana_do_mes(data):
    return ((data.day - 1) // 7) + 1


def _horario_valido(horario):
    return bool(re.match(r"^\d{2}:\d{2}$", horario))


def _horario_conflita(h1, h2):
    return h1 is None or h2 is None or h1 == h2


def _semana_conflita(s1, s2):
    return s1 is None or s2 is None or s1 == s2


def _listar_ministros_paroquia():
    return Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Ministro.nome.asc()).all()


def _get_ministro_do_form():
    ministro_id = request.form.get("ministro", type=int)
    ministro = Ministro.query.filter_by(
        id=ministro_id,
        id_paroquia=current_user.id_paroquia
    ).first()
    return ministro_id, ministro


def _conflito_data_com_data(modelo, ministro_id, data_ref, horario_ref):
    regras = modelo.query.filter_by(
        id_ministro=ministro_id,
        id_paroquia=current_user.id_paroquia,
        data=data_ref
    ).all()
    return any(_horario_conflita(horario_ref, r.horario) for r in regras)


def _conflito_data_com_fixa(modelo_fixo, ministro_id, data_ref, horario_ref):
    regras = modelo_fixo.query.filter_by(
        id_ministro=ministro_id,
        id_paroquia=current_user.id_paroquia,
        dia_semana=data_ref.weekday()
    ).all()

    semana = _semana_do_mes(data_ref)

    return any(
        _semana_conflita(semana, r.semana) and _horario_conflita(horario_ref, r.horario)
        for r in regras
    )


def _conflito_fixa_com_fixa(modelo_fixo, ministro_id, semana, dia_semana, horario):
    regras = modelo_fixo.query.filter_by(
        id_ministro=ministro_id,
        id_paroquia=current_user.id_paroquia,
        dia_semana=dia_semana
    ).all()

    return any(
        _semana_conflita(semana, r.semana) and _horario_conflita(horario, r.horario)
        for r in regras
    )


@indisp_bp.route("/indisponibilidade")
@login_required
def listar_indisponibilidade():

    indisponibilidades_fixas = IndisponibilidadeFixa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(
        IndisponibilidadeFixa.semana.asc(),
        IndisponibilidadeFixa.dia_semana.asc(),
        IndisponibilidadeFixa.horario.asc(),
        IndisponibilidadeFixa.id.desc()
    ).all()

    indisponibilidades_data = Indisponibilidade.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(
        Indisponibilidade.data.desc(),
        Indisponibilidade.horario.asc(),
        Indisponibilidade.id.desc()
    ).all()

    disponibilidades_fixas = DisponibilidadeFixa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(
        DisponibilidadeFixa.semana.asc(),
        DisponibilidadeFixa.dia_semana.asc(),
        DisponibilidadeFixa.horario.asc(),
        DisponibilidadeFixa.id.desc()
    ).all()

    disponibilidades_data = Disponibilidade.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(
        Disponibilidade.data.desc(),
        Disponibilidade.horario.asc(),
        Disponibilidade.id.desc()
    ).all()

    return render_template(
        "indisponibilidade.html",
        indisponibilidades_fixas=indisponibilidades_fixas,
        indisponibilidades_data=indisponibilidades_data,
        disponibilidades_fixas=disponibilidades_fixas,
        disponibilidades_data=disponibilidades_data,
    )


@indisp_bp.route("/indisponibilidade/nova", methods=["GET", "POST"])
@login_required
@admin_required
def nova_indisponibilidade():

    ministros = _listar_ministros_paroquia()

    if request.method == "POST":

        ministro_id, ministro = _get_ministro_do_form()

        if not ministro:
            abort(403)

        tipo_regra = (request.form.get("tipo_regra") or "fixa").strip()

        horario = (request.form.get("horario") or "").strip() or None

        if horario and not _horario_valido(horario):
            flash("Horario invalido. Use o formato HH:MM.")
            return redirect(url_for("indisponibilidade.nova_indisponibilidade"))

        if tipo_regra == "pontual":

            data_str = (request.form.get("data_especifica") or "").strip()

            try:
                data_ref = datetime.strptime(data_str, "%Y-%m-%d").date()

            except ValueError:

                flash("Informe uma data especifica valida.")

                return redirect(url_for("indisponibilidade.nova_indisponibilidade"))

            if _conflito_data_com_data(Disponibilidade, ministro_id, data_ref, horario) or _conflito_data_com_fixa(
                DisponibilidadeFixa, ministro_id, data_ref, horario
            ):

                flash("Conflito: ja existe disponibilidade nesta data/semana para este ministro.")

                return redirect(url_for("indisponibilidade.nova_indisponibilidade"))

            regra = Indisponibilidade(
                id_ministro=ministro_id,
                id_paroquia=current_user.id_paroquia,
                data=data_ref,
                horario=horario
            )

            db.session.add(regra)

            db.session.commit()

            flash("Indisponibilidade por data cadastrada com sucesso.")

            return redirect(url_for("indisponibilidade.listar_indisponibilidade"))

        dias = request.form.getlist("dias_semana[]")
        semanas = request.form.getlist("semanas[]")

        if not dias:

            flash("Selecione pelo menos um dia da semana.")

            return redirect(url_for("indisponibilidade.nova_indisponibilidade"))

        dias = [int(d) for d in dias]

        if semanas:
            semanas = [int(s) for s in semanas]
        else:
            semanas = [None]

        for dia in dias:

            for semana in semanas:

                if _conflito_fixa_com_fixa(
                        DisponibilidadeFixa,
                        ministro_id,
                        semana,
                        dia,
                        horario
                ):
                    continue

                regra = IndisponibilidadeFixa(
                    id_ministro=ministro_id,
                    id_paroquia=current_user.id_paroquia,
                    semana=semana,
                    dia_semana=dia,
                    horario=horario
                )

                db.session.add(regra)

        db.session.commit()

        flash("Indisponibilidades cadastradas com sucesso.")

        return redirect(url_for("indisponibilidade.listar_indisponibilidade"))

    return render_template("nova_indisponibilidade.html", ministros=ministros)

@indisp_bp.route("/mapa_disponibilidade")
@login_required
def mapa_disponibilidade():

    ministros = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Ministro.nome).all()

    dias_semana = range(7)

    mapa = []

    for m in ministros:

        linha = []

        for d in dias_semana:

            disp = DisponibilidadeFixa.query.filter_by(
                id_ministro=m.id,
                dia_semana=d
            ).first()

            indisp = IndisponibilidadeFixa.query.filter_by(
                id_ministro=m.id,
                dia_semana=d
            ).first()

            if indisp:
                linha.append("❌")
            elif disp:
                linha.append("✔")
            else:
                linha.append("")

        mapa.append({
            "nome": m.nome,
            "dias": linha
        })

    return render_template(
        "mapa_disponibilidade.html",
        mapa=mapa
    )

@indisp_bp.route("/disponibilidade/nova", methods=["GET", "POST"])
@login_required
@admin_required
def nova_disponibilidade():

    ministros = _listar_ministros_paroquia()

    if request.method == "POST":

        ministro_id, ministro = _get_ministro_do_form()

        if not ministro:
            abort(403)

        horario = request.form.get("horario") or None

        dias = request.form.getlist("dias_semana[]")
        semanas = request.form.getlist("semanas[]")

        dias = [int(d) for d in dias]

        if semanas:
            semanas = [int(s) for s in semanas]
        else:
            semanas = [None]

        for dia in dias:

            for semana in semanas:

                regra = DisponibilidadeFixa(
                    id_ministro=ministro_id,
                    id_paroquia=current_user.id_paroquia,
                    semana=semana,
                    dia_semana=dia,
                    horario=horario
                )

                db.session.add(regra)

        db.session.commit()

        flash("Disponibilidade cadastrada com sucesso.")

        return redirect(url_for("indisponibilidade.listar_indisponibilidade"))

    return render_template("nova_disponibilidade.html", ministros=ministros)