from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import logging

from models import db, Ministro, Paroquia
from services.firebase_service import enviar_push


auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

RESET_SALT = "sgme-reset-senha"
RESET_TOKEN_MAX_AGE_SECONDS = 3600


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def gerar_token(email):
    return _serializer().dumps(email, salt=RESET_SALT)


def validar_token(token):
    try:
        return _serializer().loads(
            token,
            salt=RESET_SALT,
            max_age=RESET_TOKEN_MAX_AGE_SECONDS
        )
    except (BadSignature, SignatureExpired):
        return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_input = request.form["login"].strip()
        senha = request.form["senha"]

        login_limpo = (
            login_input
            .replace(".", "")
            .replace("-", "")
            .replace("(", "")
            .replace(")", "")
            .replace(" ", "")
        )

        user = Ministro.query.filter(
            (Ministro.email == login_input)
            | (Ministro.cpf == login_limpo)
            | (Ministro.telefone == login_limpo)
        ).first()

        if user and user.pode_logar and user.check_senha(senha):
            login_user(user)
            if user.primeiro_acesso:
                return redirect(url_for("auth.trocar_senha"))
            return redirect(url_for("dashboard.home"))

        flash("Email ou senha invalidos ou sem permissao de acesso.")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/trocar-senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    if request.method == "POST":
        nova = request.form["nova_senha"]
        confirmar = request.form["confirmar_senha"]

        if nova != confirmar:
            flash("As senhas nao coincidem.")
            return redirect(url_for("auth.trocar_senha"))

        current_user.set_senha(nova)
        current_user.primeiro_acesso = False
        db.session.commit()

        flash("Senha alterada com sucesso.")
        return redirect(url_for("dashboard.home"))

    return render_template("trocar_senha.html")


@auth_bp.route("/reset-senha", methods=["GET", "POST"])
def reset_senha():
    if request.method == "POST":
        email = request.form["email"].strip()
        user = Ministro.query.filter_by(email=email).first()

        if user:
            token = gerar_token(email)
            link = url_for("auth.nova_senha", token=token, _external=True)
            logger.info("Link de reset gerado para email=%s: %s", email, link)

        flash("Se o email existir, o link de redefinicao foi gerado.")
        return redirect(url_for("auth.login"))

    return render_template("reset_senha.html")


@auth_bp.route("/nova-senha/<token>", methods=["GET", "POST"])
def nova_senha(token):
    email = validar_token(token)

    if not email:
        flash("Token invalido ou expirado.")
        return redirect(url_for("auth.login"))

    user = Ministro.query.filter_by(email=email).first()
    if not user:
        flash("Usuario nao encontrado para este token.")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        nova = request.form["nova_senha"]
        user.set_senha(nova)
        user.primeiro_acesso = False
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

        cpf = cpf.replace(".", "").replace("-", "")
        telefone = (
            telefone.replace("(", "")
            .replace(")", "")
            .replace("-", "")
            .replace(" ", "")
        )

        existente = Ministro.query.filter(
            (Ministro.email == email) | (Ministro.cpf == cpf)
        ).first()

        if existente:
            flash("Email ou CPF ja cadastrado.")
            return redirect(url_for("auth.cadastro"))

        paroquia = Paroquia.query.first()
        if not paroquia:
            paroquia = Paroquia(nome="Paroquia Matriz")
            db.session.add(paroquia)
            db.session.commit()

        novo = Ministro(
            nome=nome,
            email=email,
            cpf=cpf,
            telefone=telefone,
            comunidade=comunidade,
            tipo="ministro",
            pode_logar=False,
            primeiro_acesso=False,
            id_paroquia=paroquia.id,
        )
        novo.set_senha(senha)

        db.session.add(novo)
        db.session.commit()

        admin = Ministro.query.filter_by(tipo="admin").first()
        if admin and admin.firebase_token:
            enviar_push(
                admin.firebase_token,
                "Novo Cadastro",
                f"{nome} solicitou cadastro no SGME."
            )

        flash("Cadastro realizado com sucesso! Aguarde aprovacao do administrador.")
        return redirect(url_for("auth.login"))

    return render_template("cadastro.html")


@auth_bp.route("/salvar-token", methods=["POST"])
@login_required
def salvar_token():
    data = request.get_json() or {}
    token = data.get("token")
    if not token:
        return {"status": "erro", "mensagem": "token ausente"}, 400

    current_user.firebase_token = token
    db.session.commit()
    return {"status": "ok"}
