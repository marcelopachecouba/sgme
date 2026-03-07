from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from models import (
    CasalMinisterio,
    Disponibilidade,
    DisponibilidadeFixa,
    db,
    Escala,
    EscalaFixa,
    Indisponibilidade,
    IndisponibilidadeFixa,
    Ministro,
    Mural,
    MuralPost,
)
from datetime import datetime
from sqlalchemy import or_
from utils.auth import admin_required
from services.paroquia_scope_service import get_ministro_or_404

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



@ministros_bp.route("/ministros/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_ministro(id):

    ministro = get_ministro_or_404(id, current_user.id_paroquia)

    if ministro.id == current_user.id:
        flash("Nao e permitido excluir o proprio usuario logado.")
        return redirect(url_for("ministros.ministros"))

    try:
        Escala.query.filter_by(
            id_ministro=ministro.id,
            id_paroquia=current_user.id_paroquia
        ).delete(synchronize_session=False)

        EscalaFixa.query.filter_by(
            id_ministro=ministro.id,
            id_paroquia=current_user.id_paroquia
        ).delete(synchronize_session=False)

        Indisponibilidade.query.filter_by(
            id_ministro=ministro.id,
            id_paroquia=current_user.id_paroquia
        ).delete(synchronize_session=False)

        IndisponibilidadeFixa.query.filter_by(
            id_ministro=ministro.id,
            id_paroquia=current_user.id_paroquia
        ).delete(synchronize_session=False)

        Disponibilidade.query.filter_by(
            id_ministro=ministro.id,
            id_paroquia=current_user.id_paroquia
        ).delete(synchronize_session=False)

        DisponibilidadeFixa.query.filter_by(
            id_ministro=ministro.id,
            id_paroquia=current_user.id_paroquia
        ).delete(synchronize_session=False)

        Mural.query.filter_by(
            id_ministro=ministro.id,
            id_paroquia=current_user.id_paroquia
        ).delete(synchronize_session=False)

        MuralPost.query.filter_by(
            id_ministro=ministro.id,
            id_paroquia=current_user.id_paroquia
        ).delete(synchronize_session=False)

        CasalMinisterio.query.filter(
            CasalMinisterio.id_paroquia == current_user.id_paroquia,
            or_(
                CasalMinisterio.id_ministro_1 == ministro.id,
                CasalMinisterio.id_ministro_2 == ministro.id,
            )
        ).delete(synchronize_session=False)

        db.session.delete(ministro)
        db.session.commit()
        flash("Ministro excluido com sucesso.")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Erro ao excluir ministro. Verifique se existem vinculos pendentes.")

    return redirect(url_for("ministros.ministros"))

# ======================
# MISSAS
# ======================


@ministros_bp.route("/ministros/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_ministro(id):

    ministro = get_ministro_or_404(id, current_user.id_paroquia)

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

@ministros_bp.route("/admin/resetar-senha/<int:id>")
@login_required
@admin_required
def admin_resetar_senha(id):

    #if current_user.tipo != "admin":
    #    return "Acesso negado"

    user = get_ministro_or_404(id, current_user.id_paroquia)
    user.set_senha("123456")
    user.primeiro_acesso = True

    db.session.commit()

    flash("Senha redefinida para 123456")
    return redirect(url_for("ministros.ministros"))


@ministros_bp.route("/ativar_usuario/<int:id>")
@login_required
@admin_required
def ativar_usuario(id):

    user = get_ministro_or_404(id, current_user.id_paroquia)
    user.pode_logar = True
    db.session.commit()

    flash("Usuário liberado com sucesso!")
    return redirect(url_for("ministros.ministros"))
