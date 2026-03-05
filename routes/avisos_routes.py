from flask import Blueprint, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
from models import db, Aviso
import os

avisos_bp = Blueprint("avisos", __name__)

UPLOAD_FOLDER = "static/uploads"


@avisos_bp.route("/avisos")
def avisos():

    lista = Aviso.query.order_by(Aviso.data.desc()).all()

    return render_template("avisos.html", avisos=lista)


@avisos_bp.route("/avisos/novo", methods=["GET","POST"])
def novo_aviso():

    if request.method == "POST":

        titulo = request.form["titulo"]
        mensagem = request.form["mensagem"]
        tipo = request.form["tipo"]
        video_url = request.form.get("video_url")

        fixado = True if request.form.get("fixado") else False

        arquivo_nome = None

        arquivo = request.files.get("arquivo")

        if arquivo and arquivo.filename != "":

            nome = secure_filename(arquivo.filename)

            UPLOAD_FOLDER = "static/uploads"

            # cria pasta se não existir
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)

            caminho = os.path.join(UPLOAD_FOLDER, arquivo.filename)

            arquivo.save(caminho)
            arquivo_nome = nome

        aviso = Aviso(
            titulo=titulo,
            mensagem=mensagem,
            tipo=tipo,
            arquivo=arquivo_nome,
            video_url=video_url,
            fixado=fixado
        )

        db.session.add(aviso)
        db.session.commit()

        return redirect(url_for("avisos.avisos"))

    return render_template("novo_aviso.html")