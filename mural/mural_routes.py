from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from models import db, MuralPost, MuralCurtida, MuralComentario
from services.firebase_storage_service import upload_arquivo

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

        if imagem:
            imagem_url = upload_arquivo(imagem)

        if video:
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

    texto = request.form.get("comentario")

    comentario = MuralComentario(
        comentario=texto,
        id_post=post_id,
        id_ministro=current_user.id
    )

    db.session.add(comentario)
    db.session.commit()

    return redirect(url_for("mural.mural"))

@mural_bp.route("/mural/curtir/<int:post_id>")
@login_required
def curtir(post_id):

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