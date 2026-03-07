import os
import uuid
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from models import Ministro, PresencaReuniao, ReuniaoFormacao, db
from services.firebase_storage_service import upload_arquivo
from utils.auth import admin_required


presencas_bp = Blueprint("presencas", __name__)
UPLOAD_FOLDER = "static/uploads"


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

    try:
        arquivo.stream.seek(0)
        return upload_arquivo(arquivo)
    except Exception:
        arquivo.stream.seek(0)
        nome_unico = f"{uuid.uuid4().hex}_{nome_original}"
        pasta_upload = os.path.join(current_app.root_path, UPLOAD_FOLDER)
        os.makedirs(pasta_upload, exist_ok=True)
        caminho = os.path.join(pasta_upload, nome_unico)
        arquivo.save(caminho)
        return nome_unico


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
        except OSError:
            flash("Erro ao gravar foto/video enviado.")
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
        except OSError:
            flash("Erro ao gravar foto/video enviado.")
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
