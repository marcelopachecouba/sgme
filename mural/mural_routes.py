from flask import Blueprint, render_template, request, redirect, url_for, abort
from flask_login import login_required, current_user
from models import db, MuralPost, MuralCurtida, MuralComentario
from services.firebase_storage_service import upload_arquivo
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "mp4", "mov", "webm"}


def _arquivo_permitido(file):
    if not file or not file.filename:
        return False
    nome = secure_filename(file.filename)
    return "." in nome and nome.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_post_da_paroquia(post_id):
    post = MuralPost.query.filter_by(
        id=post_id,
        id_paroquia=current_user.id_paroquia
    ).first()
    if not post:
        abort(403)
    return post

mural_bp = Blueprint("mural", __name__)


@mural_bp.route("/mural")
@login_required
def mural():

    posts = MuralPost.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(MuralPost.data.desc()).all()

    return render_template("mural.html", posts=posts)


@mural_bp.route("/mural/novo", methods=["GET","POST"])
@login_required
def novo_post():

    if request.method == "POST":

        texto = request.form.get("texto")

        imagem = request.files.get("imagem")
        video = request.files.get("video")

        imagem_url = None
        video_url = None

        if imagem and _arquivo_permitido(imagem):
            imagem_url = upload_arquivo(imagem)

        if video and _arquivo_permitido(video):
            video_url = upload_arquivo(video)

        post = MuralPost(
            texto=texto,
            imagem=imagem_url,
            video=video_url,
            id_ministro=current_user.id,
            id_paroquia=current_user.id_paroquia
        )

        db.session.add(post)
        db.session.commit()

        return redirect(url_for("mural.mural"))

    return render_template("novo_post.html")

@mural_bp.route("/mural/comentar/<int:post_id>", methods=["POST"])
@login_required
def comentar(post_id):
    _get_post_da_paroquia(post_id)

    texto = request.form.get("comentario")

    comentario = MuralComentario(
        comentario=texto,
        id_post=post_id,
        id_ministro=current_user.id
    )

    db.session.add(comentario)
    db.session.commit()

    return redirect(url_for("mural.mural"))

@mural_bp.route("/mural/curtir/<int:post_id>", methods=["POST"])
@login_required
def curtir(post_id):
    _get_post_da_paroquia(post_id)

    existe = MuralCurtida.query.filter_by(
        id_post=post_id,
        id_ministro=current_user.id
    ).first()

    if not existe:

        curtida = MuralCurtida(
            id_post=post_id,
            id_ministro=current_user.id
        )

        db.session.add(curtida)
        db.session.commit()

    return redirect(url_for("mural.mural"))
