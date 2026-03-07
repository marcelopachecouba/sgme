from flask import Blueprint, render_template, redirect, request, url_for, flash, send_file
from flask_login import login_required, current_user, login_user, logout_user
from models import db, Paroquia, Ministro, Missa, Escala, Indisponibilidade, EscalaFixa
from datetime import datetime, date, timedelta
import calendar, uuid, urllib.parse, base64, io
from utils.auth import admin_required

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/criar-admin", methods=["POST"])
@login_required
@admin_required
def criar_admin():

    paroquia = Paroquia.query.first()

    if not paroquia:
        paroquia = Paroquia(nome="Paróquia Matriz")
        db.session.add(paroquia)
        db.session.commit()

    admin_existente = Ministro.query.filter_by(
        email="marcelosouzapacheco@gmail.com"
    ).first()

    if not admin_existente:
        admin = Ministro(
            nome="Marcelo",
            email="marcelosouzapacheco@gmail.com",
            tipo="admin",
            pode_logar=True,
            id_paroquia=paroquia.id
        )
        admin.set_senha("123456")
        admin.primeiro_acesso = True

        db.session.add(admin)
        db.session.commit()

        return "Admin criado com sucesso!"

    return "Admin já existe!"

@admin_bp.app_errorhandler(403)
def acesso_negado(e):
    return render_template("403.html"), 403
