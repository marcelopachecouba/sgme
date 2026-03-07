from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import Ministro, PresencaReuniao, ReuniaoFormacao, db
from utils.auth import admin_required


presencas_bp = Blueprint("presencas", __name__)


def _parse_data(valor):
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _listar_ministros_paroquia():
    return Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Ministro.nome.asc()).all()


@presencas_bp.route("/presencas")
@login_required
@admin_required
def listar_presencas():
    reunioes = ReuniaoFormacao.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(ReuniaoFormacao.data.desc(), ReuniaoFormacao.id.desc()).all()

    return render_template("presencas.html", reunioes=reunioes)


@presencas_bp.route("/presencas/nova", methods=["GET", "POST"])
@login_required
@admin_required
def nova_presenca():
    ministros = _listar_ministros_paroquia()

    if request.method == "POST":
        data_evento = _parse_data(request.form.get("data"))
        assunto = (request.form.get("assunto") or "").strip()
        tipo = (request.form.get("tipo") or "reuniao").strip()
        observacao = (request.form.get("observacao") or "").strip() or None
        presentes_ids = {
            int(x) for x in request.form.getlist("presentes") if x.isdigit()
        }

        if not data_evento or not assunto:
            flash("Informe data e assunto.")
            return render_template("presenca_form.html", ministros=ministros, reuniao=None)

        reuniao = ReuniaoFormacao(
            data=data_evento,
            assunto=assunto,
            tipo=tipo if tipo in {"reuniao", "formacao"} else "reuniao",
            observacao=observacao,
            id_paroquia=current_user.id_paroquia
        )
        db.session.add(reuniao)
        db.session.flush()

        ministros_validos = {m.id for m in ministros}
        for ministro_id in presentes_ids.intersection(ministros_validos):
            db.session.add(
                PresencaReuniao(
                    id_reuniao=reuniao.id,
                    id_ministro=ministro_id,
                    id_paroquia=current_user.id_paroquia,
                    presente=True
                )
            )

        db.session.commit()
        flash("Presenca registrada com sucesso.")
        return redirect(url_for("presencas.listar_presencas"))

    return render_template("presenca_form.html", ministros=ministros, reuniao=None)


@presencas_bp.route("/presencas/editar/<int:reuniao_id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_presenca(reuniao_id):
    reuniao = ReuniaoFormacao.query.filter_by(
        id=reuniao_id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()
    ministros = _listar_ministros_paroquia()

    if request.method == "POST":
        data_evento = _parse_data(request.form.get("data"))
        assunto = (request.form.get("assunto") or "").strip()
        tipo = (request.form.get("tipo") or "reuniao").strip()
        observacao = (request.form.get("observacao") or "").strip() or None
        presentes_ids = {
            int(x) for x in request.form.getlist("presentes") if x.isdigit()
        }

        if not data_evento or not assunto:
            flash("Informe data e assunto.")
            presentes_atual = {p.id_ministro for p in reuniao.presencas if p.presente}
            return render_template(
                "presenca_form.html",
                ministros=ministros,
                reuniao=reuniao,
                presentes_ids=presentes_atual
            )

        reuniao.data = data_evento
        reuniao.assunto = assunto
        reuniao.tipo = tipo if tipo in {"reuniao", "formacao"} else "reuniao"
        reuniao.observacao = observacao

        ministros_validos = {m.id for m in ministros}
        presentes_validos = presentes_ids.intersection(ministros_validos)

        PresencaReuniao.query.filter_by(
            id_reuniao=reuniao.id,
            id_paroquia=current_user.id_paroquia
        ).delete(synchronize_session=False)

        for ministro_id in presentes_validos:
            db.session.add(
                PresencaReuniao(
                    id_reuniao=reuniao.id,
                    id_ministro=ministro_id,
                    id_paroquia=current_user.id_paroquia,
                    presente=True
                )
            )

        db.session.commit()
        flash("Presencas atualizadas.")
        return redirect(url_for("presencas.listar_presencas"))

    presentes_atual = {p.id_ministro for p in reuniao.presencas if p.presente}
    return render_template(
        "presenca_form.html",
        ministros=ministros,
        reuniao=reuniao,
        presentes_ids=presentes_atual
    )


@presencas_bp.route("/presencas/excluir/<int:reuniao_id>", methods=["POST"])
@login_required
@admin_required
def excluir_presenca(reuniao_id):
    reuniao = ReuniaoFormacao.query.filter_by(
        id=reuniao_id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()

    db.session.delete(reuniao)
    db.session.commit()
    flash("Registro de presenca excluido.")
    return redirect(url_for("presencas.listar_presencas"))

