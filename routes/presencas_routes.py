from collections import defaultdict
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import extract
from werkzeug.utils import secure_filename

from models import Ministro, PresencaReuniao, ReuniaoFormacao, db
from services.firebase_storage_service import upload_arquivo
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


def _salvar_upload(campo_arquivo):
    arquivo = request.files.get(campo_arquivo)
    if not arquivo or arquivo.filename == "":
        return None

    nome_original = secure_filename(arquivo.filename)
    if not nome_original:
        return None

    arquivo.stream.seek(0)
    # Upload obrigatorio no Firebase para evitar perda de arquivo em disco efemero.
    return upload_arquivo(arquivo)


@presencas_bp.route("/presencas")
@login_required
@admin_required
def listar_presencas():
    reunioes = ReuniaoFormacao.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(ReuniaoFormacao.data.desc(), ReuniaoFormacao.id.desc()).all()

    return render_template("presencas.html", reunioes=reunioes)


@presencas_bp.route("/presencas/relatorio")
@login_required
@admin_required
def relatorio_presencas():
    ano_atual = datetime.utcnow().year
    ano = request.args.get("ano", type=int) or ano_atual

    anos_rows = db.session.query(
        extract("year", ReuniaoFormacao.data)
    ).filter(
        ReuniaoFormacao.id_paroquia == current_user.id_paroquia
    ).distinct().order_by(
        extract("year", ReuniaoFormacao.data).desc()
    ).all()

    anos_disponiveis = sorted(
        {
            int(row[0])
            for row in anos_rows
            if row and row[0] is not None
        },
        reverse=True
    )
    if ano not in anos_disponiveis:
        anos_disponiveis = sorted({ano, *anos_disponiveis}, reverse=True)

    ministros = _listar_ministros_paroquia()

    reunioes_ano = ReuniaoFormacao.query.filter(
        ReuniaoFormacao.id_paroquia == current_user.id_paroquia,
        extract("year", ReuniaoFormacao.data) == ano
    ).order_by(
        ReuniaoFormacao.data.asc(),
        ReuniaoFormacao.id.asc()
    ).all()

    datas = sorted({r.data for r in reunioes_ano})

    presencas_rows = db.session.query(
        PresencaReuniao.id_ministro,
        ReuniaoFormacao.data
    ).join(
        ReuniaoFormacao, PresencaReuniao.id_reuniao == ReuniaoFormacao.id
    ).filter(
        PresencaReuniao.id_paroquia == current_user.id_paroquia,
        ReuniaoFormacao.id_paroquia == current_user.id_paroquia,
        PresencaReuniao.presente.is_(True),
        extract("year", ReuniaoFormacao.data) == ano
    ).all()

    presenca_map = defaultdict(set)
    for ministro_id, data in presencas_rows:
        presenca_map[ministro_id].add(data)

    return render_template(
        "presencas_relatorio.html",
        ano=ano,
        anos_disponiveis=anos_disponiveis,
        datas=datas,
        ministros=ministros,
        presenca_map=presenca_map
    )


@presencas_bp.route("/presencas/imprimir/<int:reuniao_id>")
@login_required
@admin_required
def imprimir_presenca(reuniao_id):
    reuniao = ReuniaoFormacao.query.filter_by(
        id=reuniao_id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()

    ministros_presentes = sorted(
        [
            p.ministro.nome
            for p in reuniao.presencas
            if p.presente and p.ministro and p.ministro.nome
        ],
        key=lambda nome: nome.lower()
    )

    return render_template(
        "presenca_impressao.html",
        reuniao=reuniao,
        ministros_presentes=ministros_presentes
    )


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
        video_url = (request.form.get("video_url") or "").strip() or None
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
            video_url=video_url,
            id_paroquia=current_user.id_paroquia
        )

        try:
            reuniao.foto_url = _salvar_upload("foto")
            reuniao.video_arquivo_url = _salvar_upload("video_arquivo")
        except Exception:
            flash("Erro ao enviar foto/video para o Firebase. Tente novamente.")
            return render_template("presenca_form.html", ministros=ministros, reuniao=None)

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
        video_url = (request.form.get("video_url") or "").strip() or None
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
        reuniao.video_url = video_url

        if request.form.get("remover_foto"):
            reuniao.foto_url = None
        if request.form.get("remover_video_arquivo"):
            reuniao.video_arquivo_url = None
        if request.form.get("remover_video_url"):
            reuniao.video_url = None

        try:
            foto_url = _salvar_upload("foto")
            video_arquivo_url = _salvar_upload("video_arquivo")
        except Exception:
            flash("Erro ao enviar foto/video para o Firebase. Tente novamente.")
            presentes_atual = {p.id_ministro for p in reuniao.presencas if p.presente}
            return render_template(
                "presenca_form.html",
                ministros=ministros,
                reuniao=reuniao,
                presentes_ids=presentes_atual
            )

        if foto_url:
            reuniao.foto_url = foto_url
        if video_arquivo_url:
            reuniao.video_arquivo_url = video_arquivo_url

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
