import re
from collections import defaultdict
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import (
    Disponibilidade,
    DisponibilidadeFixa,
    Indisponibilidade,
    IndisponibilidadeFixa,
    Ministro,
    Missa,
    db,
)
from utils.auth import admin_required


indisp_bp = Blueprint("indisponibilidade", __name__)

DIAS_SEMANA_LABEL = {
    0: "SEG",
    1: "TER",
    2: "QUA",
    3: "QUI",
    4: "SEX",
    5: "SAB",
    6: "DOM",
}


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


def _regra_indisponibilidade_fixa(ministro_id, dia_semana, horario):
    regras = IndisponibilidadeFixa.query.filter_by(
        id_ministro=ministro_id,
        dia_semana=dia_semana,
        id_paroquia=current_user.id_paroquia
    ).all()

    for regra in regras:
        if regra.horario is None or regra.horario == horario:
            return regra

    return None


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

            db.session.add(
                Indisponibilidade(
                    id_ministro=ministro_id,
                    id_paroquia=current_user.id_paroquia,
                    data=data_ref,
                    horario=horario
                )
            )
            db.session.commit()

            flash("Indisponibilidade por data cadastrada com sucesso.")
            return redirect(url_for("indisponibilidade.listar_indisponibilidade"))

        dias = [int(d) for d in request.form.getlist("dias_semana[]")]
        semanas_raw = request.form.getlist("semanas[]")

        if not dias:
            flash("Selecione pelo menos um dia da semana.")
            return redirect(url_for("indisponibilidade.nova_indisponibilidade"))

        if not semanas_raw or "" in semanas_raw:
            semanas = [None]
        else:
            semanas = [int(s) for s in semanas_raw]

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

                db.session.add(
                    IndisponibilidadeFixa(
                        id_ministro=ministro_id,
                        id_paroquia=current_user.id_paroquia,
                        semana=semana,
                        dia_semana=dia,
                        horario=horario
                    )
                )

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

    missas = Missa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).all()

    colunas_por_dia = defaultdict(set)
    for missa in missas:
        if missa.horario:
            colunas_por_dia[missa.data.weekday()].add(missa.horario)

    colunas = []
    for dia in range(7):
        for horario in sorted(colunas_por_dia.get(dia, [])):
            colunas.append({
                "dia_semana": dia,
                "dia_label": DIAS_SEMANA_LABEL[dia],
                "horario": horario,
            })

    mapa = []
    for ministro in ministros:
        celulas = []
        for coluna in colunas:
            regra = _regra_indisponibilidade_fixa(
                ministro.id,
                coluna["dia_semana"],
                coluna["horario"]
            )
            celulas.append({
                "simbolo": "X" if regra else "O",
                "dia_semana": coluna["dia_semana"],
                "horario": coluna["horario"],
            })

        mapa.append({
            "id": ministro.id,
            "nome": ministro.nome,
            "celulas": celulas,
        })

    return render_template(
        "mapa_disponibilidade.html",
        mapa=mapa,
        colunas=colunas
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
        dias = [int(d) for d in request.form.getlist("dias_semana[]")]
        semanas_raw = request.form.getlist("semanas[]")

        if not semanas_raw or "" in semanas_raw:
            semanas = [None]
        else:
            semanas = [int(s) for s in semanas_raw]

        for dia in dias:
            for semana in semanas:
                db.session.add(
                    DisponibilidadeFixa(
                        id_ministro=ministro_id,
                        id_paroquia=current_user.id_paroquia,
                        semana=semana,
                        dia_semana=dia,
                        horario=horario
                    )
                )

        db.session.commit()
        flash("Disponibilidade cadastrada com sucesso.")
        return redirect(url_for("indisponibilidade.listar_indisponibilidade"))

    return render_template("nova_disponibilidade.html", ministros=ministros)


@indisp_bp.route("/indisponibilidade/fixa/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_indisponibilidade_fixa(id):
    regra = IndisponibilidadeFixa.query.filter_by(
        id=id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()

    db.session.delete(regra)
    db.session.commit()

    flash("Indisponibilidade fixa removida.")
    return redirect(url_for("indisponibilidade.listar_indisponibilidade"))


@indisp_bp.route("/indisponibilidade/data/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_indisponibilidade_data(id):
    regra = Indisponibilidade.query.filter_by(
        id=id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()

    db.session.delete(regra)
    db.session.commit()

    flash("Indisponibilidade removida.")
    return redirect(url_for("indisponibilidade.listar_indisponibilidade"))


@indisp_bp.route("/disponibilidade/fixa/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_disponibilidade_fixa(id):
    regra = DisponibilidadeFixa.query.filter_by(
        id=id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()

    db.session.delete(regra)
    db.session.commit()

    flash("Disponibilidade removida.")
    return redirect(url_for("indisponibilidade.listar_indisponibilidade"))


@indisp_bp.route("/disponibilidade/data/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_disponibilidade_data(id):
    regra = Disponibilidade.query.filter_by(
        id=id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()

    db.session.delete(regra)
    db.session.commit()

    flash("Disponibilidade removida.")
    return redirect(url_for("indisponibilidade.listar_indisponibilidade"))


@indisp_bp.route("/indisponibilidade/ministro/limpar/<int:ministro_id>", methods=["POST"])
@login_required
@admin_required
def limpar_indisponibilidades_ministro(ministro_id):
    ministro = Ministro.query.filter_by(
        id=ministro_id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()

    IndisponibilidadeFixa.query.filter_by(
        id_ministro=ministro.id,
        id_paroquia=current_user.id_paroquia
    ).delete()

    Indisponibilidade.query.filter_by(
        id_ministro=ministro.id,
        id_paroquia=current_user.id_paroquia
    ).delete()

    db.session.commit()

    flash(f"Todas indisponibilidades de {ministro.nome} foram removidas.")
    return redirect(url_for("indisponibilidade.listar_indisponibilidade"))


@indisp_bp.route("/api/toggle_indisponibilidade", methods=["POST"])
@login_required
@admin_required
def toggle_indisponibilidade():
    ministro_id = request.json.get("ministro_id")
    dia_semana = request.json.get("dia_semana")
    horario = request.json.get("horario") or None

    regra_exata = IndisponibilidadeFixa.query.filter_by(
        id_ministro=ministro_id,
        dia_semana=dia_semana,
        horario=horario,
        id_paroquia=current_user.id_paroquia
    ).first()

    regra_ampla = None
    if not regra_exata:
        regra_ampla = IndisponibilidadeFixa.query.filter_by(
            id_ministro=ministro_id,
            dia_semana=dia_semana,
            horario=None,
            id_paroquia=current_user.id_paroquia
        ).first()

    if regra_exata:
        db.session.delete(regra_exata)
        status = "removido"
    elif regra_ampla:
        db.session.delete(regra_ampla)
        status = "removido"
    else:
        db.session.add(
            IndisponibilidadeFixa(
                id_ministro=ministro_id,
                dia_semana=dia_semana,
                semana=None,
                horario=horario,
                id_paroquia=current_user.id_paroquia
            )
        )
        status = "criado"

    db.session.commit()
    return {"status": status}


