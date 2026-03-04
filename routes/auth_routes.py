from flask import Blueprint, render_template, redirect, request, url_for, flash, send_file
from flask_login import login_required, current_user, login_user, logout_user
from models import db, Paroquia, Ministro, Missa, Escala, Indisponibilidade, EscalaFixa
from datetime import datetime, date, timedelta
import calendar, uuid, urllib.parse, base64, io
from utils.auth import admin_required

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        login_input = request.form["login"].strip()
        senha = request.form["senha"]

        # Remove pontuação do CPF e telefone
        login_limpo = (
            login_input
            .replace(".", "")
            .replace("-", "")
            .replace("(", "")
            .replace(")", "")
            .replace(" ", "")
        )

        user = Ministro.query.filter(
            (Ministro.email == login_input) |
            (Ministro.cpf == login_limpo) |
            (Ministro.telefone == login_limpo)
        ).first()
        
        # 🔐 Verifica se pode logar
        if user and user.pode_logar and user.check_senha(senha):

            login_user(user)

            # Obriga trocar senha no primeiro acesso
            if user.primeiro_acesso:
                return redirect(url_for("auth.trocar_senha"))

            return redirect(url_for("dashboard.home"))

        else:
            flash("Email ou senha inválidos ou sem permissão de acesso.")

    return render_template("login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))

# ======================
# DASHBOARD
# ======================

from datetime import date, timedelta
import urllib.parse


@auth_bp.route("/trocar-senha", methods=["GET", "POST"])
@login_required
def trocar_senha():

    if request.method == "POST":
        nova = request.form["nova_senha"]
        confirmar = request.form["confirmar_senha"]

        if nova != confirmar:
            flash("As senhas não coincidem.")
            return redirect(url_for("auth.trocar_senha"))

        current_user.set_senha(nova)
        current_user.primeiro_acesso = False
        db.session.commit()

        flash("Senha alterada com sucesso.")
        return redirect(url_for("dashboard.home"))

    return render_template("auth.trocar_senha.html")


@auth_bp.route("/reset-senha", methods=["GET", "POST"])
def reset_senha():

    if request.method == "POST":
        email = request.form["email"]
        user = Ministro.query.filter_by(email=email).first()

        if user:
            token = gerar_token(email)
            link = url_for("nova_senha", token=token, _external=True)

            print("LINK RESET:", link)  # depois você envia por email

            flash("Link de redefinição gerado. Verifique o console.")

        return redirect(url_for("auth.login"))

    return render_template("reset_senha.html")


@auth_bp.route("/nova-senha/<token>", methods=["GET", "POST"])
def nova_senha(token):

    email = validar_token(token)

    if not email:
        flash("Token inválido ou expirado.")
        return redirect(url_for("auth.login"))

    user = Ministro.query.filter_by(email=email).first()

    if request.method == "POST":
        nova = request.form["nova_senha"]
        user.set_senha(nova)
        db.session.commit()

        flash("Senha redefinida com sucesso.")
        return redirect(url_for("auth.login"))

    return render_template("nova_senha.html")


@auth_bp.route("/cadastro", methods=["GET", "POST"])
def cadastro():

    if request.method == "POST":

        nome = request.form["nome"]
        email = request.form["email"]
        senha = request.form["senha"]
        cpf = request.form["cpf"]
        telefone = request.form["telefone"]
        comunidade = request.form["comunidade"]

        # Remove máscara
        cpf = cpf.replace(".", "").replace("-", "")
        telefone = telefone.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")

        existente = Ministro.query.filter(
            (Ministro.email == email) |
            (Ministro.cpf == cpf)
        ).first()

        if existente:
            flash("Email ou CPF já cadastrado.")
            return redirect(url_for("cadastro"))

        paroquia = Paroquia.query.first()

        novo = Ministro(
            nome=nome,
            email=email,
            cpf=cpf,
            telefone=telefone,
            comunidade=comunidade,
            tipo="ministro",
            pode_logar=False,
            primeiro_acesso=False,
            id_paroquia=paroquia.id
        )

        novo.set_senha(senha)

        db.session.add(novo)
        db.session.commit()

        # 🔔 Notifica admin via Firebase (se tiver token)
        admin = Ministro.query.filter_by(tipo="admin").first()

        if admin and admin.firebase_token:
            enviar_push(
                admin.firebase_token,
                "Novo Cadastro",
                f"{nome} solicitou cadastro no SGME."
            )

        flash("Cadastro realizado com sucesso! Aguarde aprovação do administrador.")
        return redirect(url_for("auth.login"))

    return render_template("cadastro.html")


@auth_bp.route("/salvar-token", methods=["POST"])
@login_required
def salvar_token():
    data = request.get_json()
    current_user.firebase_token = data["token"]
    db.session.commit()
    return {"status": "ok"}



