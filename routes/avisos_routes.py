import os
import uuid

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import func
from werkzeug.utils import secure_filename

from models import Aviso, db
from services.firebase_storage_service import upload_arquivo
from utils.auth import admin_required


avisos_bp = Blueprint("avisos", __name__)

UPLOAD_FOLDER = "static/uploads"
CATEGORIAS = {
    "todos": None,
    "avisos": "aviso",
    "formacoes": "formacao",
    "fotos": "foto",
}


def _salvar_arquivo_upload():
    arquivo = request.files.get("arquivo")
    if not arquivo or arquivo.filename == "":
        return None

    nome_original = secure_filename(arquivo.filename)
    if not nome_original:
        return None

    # Preferencia por armazenamento persistente (Firebase Storage).
    try:
        arquivo.stream.seek(0)
        return upload_arquivo(arquivo)
    except Exception:
        # Fallback local para manter compatibilidade quando Firebase nao estiver pronto.
        arquivo.stream.seek(0)
        nome_unico = f"{uuid.uuid4().hex}_{nome_original}"
        pasta_upload = os.path.join(current_app.root_path, UPLOAD_FOLDER)
        os.makedirs(pasta_upload, exist_ok=True)
        caminho = os.path.join(pasta_upload, nome_unico)
        arquivo.save(caminho)
        return nome_unico


def _listar_avisos(categoria):
    tipo = CATEGORIAS.get(categoria)
    query = Aviso.query
    if tipo:
        query = query.filter_by(tipo=tipo)

    lista = query.order_by(
        func.coalesce(Aviso.fixado, False).desc(),
        Aviso.data.desc()
    ).all()
    return render_template(
        "avisos.html",
        avisos=lista,
        categoria_ativa=categoria,
    )


@avisos_bp.route("/avisos")
def avisos():
    return _listar_avisos("todos")


@avisos_bp.route("/avisos/categoria/<categoria>")
def avisos_categoria(categoria):
    if categoria not in CATEGORIAS:
        abort(404)
    return _listar_avisos(categoria)


@avisos_bp.route("/avisos/novo", methods=["GET", "POST"])
@login_required
@admin_required
def novo_aviso():
    if request.method == "POST":
        aviso = Aviso(
            titulo=request.form["titulo"],
            mensagem=request.form["mensagem"],
            tipo=request.form["tipo"],
            video_url=request.form.get("video_url"),
            fixado=bool(request.form.get("fixado")),
        )

        try:
            arquivo_nome = _salvar_arquivo_upload()
            if arquivo_nome:
                aviso.arquivo = arquivo_nome
        except OSError:
            flash("Erro ao gravar o arquivo enviado.")
            return redirect(url_for("avisos.novo_aviso"))

        db.session.add(aviso)
        db.session.commit()
        return redirect(url_for("avisos.avisos"))

    return render_template("novo_aviso.html")


@avisos_bp.route("/avisos/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_aviso(id):
    aviso = Aviso.query.get_or_404(id)

    if request.method == "POST":
        aviso.titulo = request.form["titulo"]
        aviso.mensagem = request.form["mensagem"]
        aviso.tipo = request.form["tipo"]
        aviso.video_url = request.form.get("video_url")
        aviso.fixado = bool(request.form.get("fixado"))

        if request.form.get("remover_arquivo"):
            aviso.arquivo = None
        if request.form.get("remover_video"):
            aviso.video_url = None

        try:
            arquivo_nome = _salvar_arquivo_upload()
            if arquivo_nome:
                aviso.arquivo = arquivo_nome
        except OSError:
            flash("Erro ao gravar o arquivo enviado.")
            return redirect(url_for("avisos.editar_aviso", id=id))

        db.session.commit()
        return redirect(url_for("avisos.avisos"))

    return render_template("editar_aviso.html", aviso=aviso)


@avisos_bp.route("/avisos/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_aviso(id):
    aviso = Aviso.query.get_or_404(id)
    db.session.delete(aviso)
    db.session.commit()
    return redirect(url_for("avisos.avisos"))
