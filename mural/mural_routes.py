from flask import Blueprint, render_template, request, redirect, url_for, abort, flash
from flask_login import login_required, current_user
from models import db, MuralPost, MuralCurtida, MuralComentario
from services.firebase_storage_service import upload_arquivo
from werkzeug.utils import secure_filename

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "jfif", "heic", "heif"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "mov", "webm"}


def _extensao_arquivo(file):
    if not file or not file.filename:
        return None
    nome = secure_filename(file.filename)
    if "." not in nome:
        return None
    return nome.rsplit(".", 1)[1].lower()


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

        ext_imagem = _extensao_arquivo(imagem)
        if imagem and imagem.filename:
            if not ext_imagem or ext_imagem not in ALLOWED_IMAGE_EXTENSIONS:
                flash("Formato de foto nao suportado. Use: png, jpg, jpeg, gif, webp, jfif, heic ou heif.")
                return render_template("novo_post.html")
            try:
                imagem_url = upload_arquivo(imagem)
            except Exception:
                flash("Erro ao enviar a foto. Verifique o Firebase e tente novamente.")
                return render_template("novo_post.html")

        ext_video = _extensao_arquivo(video)
        if video and video.filename:
            if not ext_video or ext_video not in ALLOWED_VIDEO_EXTENSIONS:
                flash("Formato de video nao suportado. Use: mp4, mov ou webm.")
                return render_template("novo_post.html")
            try:
                video_url = upload_arquivo(video)
            except Exception:
                flash("Erro ao enviar o video. Verifique o Firebase e tente novamente.")
                return render_template("novo_post.html")

        if not (texto and texto.strip()) and not imagem_url and not video_url:
            flash("Escreva uma mensagem ou envie foto/video para publicar.")
            return render_template("novo_post.html")

        post = MuralPost(
            texto=texto,
            imagem=imagem_url,
            video=video_url,
            id_ministro=current_user.id,
            id_paroquia=current_user.id_paroquia
        )

        db.session.add(post)
        db.session.commit()
        flash("Post publicado com sucesso.")

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
