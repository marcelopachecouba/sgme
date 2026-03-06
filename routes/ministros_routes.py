from flask import Blueprint, render_template, redirect, request, url_for, flash, send_file, abort
from flask_login import login_required, current_user, login_user, logout_user
from models import db, Paroquia, Ministro, Missa, Escala, Indisponibilidade, EscalaFixa
from datetime import datetime, date, timedelta
import calendar, uuid, urllib.parse, base64, io
from utils.auth import admin_required

ministros_bp = Blueprint("ministros", __name__)

@ministros_bp.route("/ministros")
@login_required
def ministros():
    lista = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).all()
    return render_template("ministros.html", ministros=lista)


@ministros_bp.route("/ministros/novo", methods=["GET", "POST"])
@login_required
@admin_required
def novo_ministro():

    if request.method == "POST":

        nome = request.form.get("nome")
        telefone = request.form.get("telefone")
        email = request.form.get("email")
        
        if email == "":
           email = None

        data_nascimento = request.form.get("data_nascimento")
        tempo_ministerio = request.form.get("tempo_ministerio")
        cpf = request.form.get("cpf")
        comunidade = request.form.get("comunidade")

        print("DEBUG:")
        print(nome, telefone, email, data_nascimento, tempo_ministerio,cpf,comunidade)

        novo = Ministro(
            nome=nome,
            telefone=telefone,
            email=email,
            data_nascimento=datetime.strptime(data_nascimento, "%Y-%m-%d") if data_nascimento else None,
            tempo_ministerio=int(tempo_ministerio) if tempo_ministerio else 0,
            cpf=cpf,
            comunidade=comunidade,
            id_paroquia=current_user.id_paroquia
        )

        # 🔐 SENHA PADRÃO
        novo.set_senha("123456")
        novo.primeiro_acesso = True
        novo.pode_logar = False   # continua aguardando liberação do admin

        novo.gerar_token()

        db.session.add(novo)

        try:
            db.session.commit()
            print("SALVOU COM SUCESSO")
        except Exception as e:
            print("ERRO AO SALVAR:", e)
            db.session.rollback()

        return redirect(url_for("ministros.ministros"))

    return render_template("novo_ministro.html")



@ministros_bp.route("/ministros/excluir/<int:id>")
@login_required
@admin_required
def excluir_ministro(id):

    ministro = Ministro.query.get_or_404(id)
    if ministro.id_paroquia != current_user.id_paroquia:
        abort(403)

    db.session.delete(ministro)
    db.session.commit()

    return redirect(url_for("ministros.ministros"))

# ======================
# MISSAS
# ======================


@ministros_bp.route("/ministros/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_ministro(id):

    ministro = Ministro.query.get_or_404(id)
    if ministro.id_paroquia != current_user.id_paroquia:
        abort(403)

    if request.method == "POST":

        novo_nome = request.form["nome"].strip()
        telefone = request.form["telefone"]
        email = request.form["email"]
        data_nascimento = request.form["data_nascimento"]
        tempo_ministerio = request.form["tempo_ministerio"]
        cpf = request.form["cpf"]
        comunidade = request.form["comunidade"]

        existe = Ministro.query.filter(
            Ministro.nome == novo_nome,
            Ministro.id_paroquia == current_user.id_paroquia,
            Ministro.id != ministro.id
        ).first()

        if existe:
            flash("Já existe outro ministro com esse nome.")
            return redirect(url_for("ministros.editar_ministro", id=id))

        ministro.nome = novo_nome
        ministro.telefone = telefone
        ministro.email = email
        ministro.data_nascimento = datetime.strptime(data_nascimento, "%Y-%m-%d") if data_nascimento else None
        ministro.tempo_ministerio = int(tempo_ministerio) if tempo_ministerio else 0
        ministro.cpf = cpf
        ministro.comunidade = comunidade

        db.session.commit()
        return redirect(url_for("ministros.ministros"))

    return render_template("editar_ministro.html", ministro=ministro)

from datetime import datetime


@ministros_bp.route("/admin/resetar-senha/<int:id>")
@login_required
@admin_required
def admin_resetar_senha(id):

    #if current_user.tipo != "admin":
    #    return "Acesso negado"

    user = Ministro.query.get_or_404(id)
    if user.id_paroquia != current_user.id_paroquia:
        abort(403)
    user.set_senha("123456")
    user.primeiro_acesso = True

    db.session.commit()

    flash("Senha redefinida para 123456")
    return redirect(url_for("ministros.ministros"))


@ministros_bp.route("/ativar_usuario/<int:id>")
@login_required
@admin_required
def ativar_usuario(id):

    user = Ministro.query.get_or_404(id)
    if user.id_paroquia != current_user.id_paroquia:
        abort(403)
    user.pode_logar = True
    db.session.commit()

    flash("Usuário liberado com sucesso!")
    return redirect(url_for("ministros.ministros"))

