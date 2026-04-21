from rifas.services import update_team, delete_team, update_vendor, delete_vendor
from rifas.services import cancelar_pagamento
from rifas.services import acesso_rifas_required
from flask import request, session, render_template, redirect, url_for, flash
from rifas.services import payment_whatsapp_link
from datetime import timedelta  # 🔥 IMPORTAR LÁ EM CIMA
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, redirect, render_template, request, send_file, url_for, flash
from flask_login import current_user, login_required, login_user
from rifas.services import cancelar_pagamentos_expirados  # 🔥 IMPORTAR LÁ EM CIMA
from utils.auth import admin_required
from extensions import db  # ✅ ADICIONADO
from models import ClienteRifa, Equipe, Ministro, PagamentoRifa, Vendedor
from sqlalchemy import func
from rifas.services import (
    RifaError,
    RifaSchemaMissingError,
    admin_dashboard_data,
    confirm_payment,
    create_team,
    create_vendor,
    create_or_update_campaign,
    generate_vendor_link,
    get_campaign,
    payment_detail_data,
)
from services.public_url_service import build_public_url

rifas_admin_bp = Blueprint("rifas_admin", __name__)


def _dados_fallback(mensagem: str) -> dict:
    return {
        "pagamentos": [],
        "clientes": [],
        "rifas": [],
        "campanhas": [],
        "campanha_ativa": None,
        "ranking_compradores": [],
        "stats": {
            "total_pago": 0,
            "disponiveis": 0,
            "reservadas": 0,
            "pagas": 0,
            "clientes": 0,
            "pagamentos": 0,
        },
        "schema_message": mensagem,
    }


def _base_context():
    try:
        return admin_dashboard_data()
    except RifaSchemaMissingError as exc:
        return _dados_fallback(str(exc))


def _parse_date(value: str):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


@rifas_admin_bp.route("/admin/rifas", methods=["GET"])
@acesso_rifas_required

def admin_rifas():
    dados = _base_context()
    return render_template("admin_rifas.html", **dados)


@rifas_admin_bp.route("/admin/pagamentos", methods=["GET"])
@acesso_rifas_required

def admin_pagamentos():
    cancelar_pagamentos_expirados()
    db.session.commit()

    status = request.args.get("status")
    data_inicio_str = request.args.get("data_inicio")
    data_fim_str = request.args.get("data_fim")

    query = db.select(PagamentoRifa)

    if status:
        query = query.where(PagamentoRifa.status == status)

    if data_inicio_str:
        data_inicio = datetime.strptime(data_inicio_str, "%Y-%m-%d")
        query = query.where(PagamentoRifa.created_at >= data_inicio)

    if data_fim_str:
        data_fim = datetime.strptime(data_fim_str, "%Y-%m-%d")
        data_fim = data_fim.replace(hour=23, minute=59, second=59)
        query = query.where(PagamentoRifa.created_at <= data_fim)

    pagamentos = db.session.execute(
        query.order_by(PagamentoRifa.created_at.desc())
    ).scalars().all()

    dados = _base_context()

    # 🔥 sobrescreve pagamentos
    dados["pagamentos"] = pagamentos
    dados["status"] = status
    dados["data_inicio"] = data_inicio_str
    dados["data_fim"] = data_fim_str

    return render_template(
        "admin_pagamentos_rifas.html",
        now=datetime.utcnow(),
        **dados
    )


@rifas_admin_bp.route("/admin/pagamentos/<payment_id>", methods=["GET"])
@acesso_rifas_required

def admin_pagamento_detalhe(payment_id):
    dados = _base_context()
    try:
        detalhe = payment_detail_data(payment_id)
        dados.update(detalhe)

        pagamento = dados.get("pagamento")

        if pagamento and pagamento.created_at:
            pagamento.expira_em = pagamento.created_at + timedelta(minutes=60)
        else:
            pagamento.expira_em = None

        # 🔥 AQUI ESTAVA FALTANDO
        from rifas.services import payment_whatsapp_link
        whatsapp_link = payment_whatsapp_link(pagamento)
        dados["whatsapp_link"] = whatsapp_link

    except RifaError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("rifas_admin.admin_pagamentos"))

    return render_template(
        "admin_pagamento_rifa_detalhe.html",
        now=datetime.utcnow(),
        **dados
    )

# ✅ CORRIGIDO
@rifas_admin_bp.route("/admin/pagamentos/<payment_id>/aprovar", methods=["POST"])
@acesso_rifas_required

def admin_pagamento_aprovar(payment_id):
    observacoes = (request.form.get("observacoes_admin") or "").strip()

    try:
        confirm_payment(pagamento_id=payment_id, observacoes_admin=observacoes)

        db.session.commit()  # ✅ ESSENCIAL

        flash("Pagamento marcado como pago com sucesso.", "success")

    except RifaError as exc:
        db.session.rollback()  # ✅ ESSENCIAL
        flash(str(exc), "danger")

    return redirect(url_for("rifas_admin.admin_pagamento_detalhe", payment_id=payment_id))


@rifas_admin_bp.route("/admin/pagamentos/<payment_id>/pdf", methods=["GET"])
@acesso_rifas_required

def admin_pagamento_pdf(payment_id):
    from datetime import datetime

    try:
        detalhe = payment_detail_data(payment_id)
    except RifaError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("rifas_admin.admin_pagamentos"))

    pagamento = detalhe["pagamento"]

    # 🔥 REGRA PRINCIPAL: SÓ PODE IMPRIMIR SE FOR PAGO
    if pagamento.status != "pago":
        flash("Só é permitido imprimir pagamentos com status PAGO.", "danger")
        return redirect(url_for("rifas_admin.admin_pagamentos"))

    # 🔥 BLOQUEIO DE REIMPRESSÃO
    #if pagamento.impresso and not request.args.get("forcar"):
     #   flash("Este pagamento já foi impresso.", "warning")
      #  return redirect(url_for("rifas_admin.admin_pagamentos"))

    # 🔥 GERA O PDF
    from rifas.pdf_generator import generate_tickets_pdf_memory

    pdf_buffer = generate_tickets_pdf_memory(
        pagamento=pagamento,
        rifas=sorted(pagamento.rifas, key=lambda r: r.numero),
        cliente=pagamento.cliente,
    )

    # 🔥 MARCA COMO IMPRESSO
    if not pagamento.impresso:
        pagamento.impresso = True
        pagamento.impresso_em = datetime.utcnow()
        db.session.commit()

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        download_name=f"rifas-{payment_id}.pdf",
        as_attachment=False
    )

@rifas_admin_bp.route("/admin/clientes", methods=["GET"])
@acesso_rifas_required

def admin_clientes():
    dados = _base_context()
    return render_template("admin_clientes_rifas.html", **dados)


@rifas_admin_bp.route("/admin/relatorio", methods=["GET"])
@acesso_rifas_required

def admin_relatorio():
    status = request.args.get("status")
    data_inicio_str = request.args.get("data_inicio")
    data_fim_str = request.args.get("data_fim")

    query = db.select(PagamentoRifa)

    if status:
        query = query.where(PagamentoRifa.status == status)

    if data_inicio_str:
        data_inicio = datetime.strptime(data_inicio_str, "%Y-%m-%d")
        query = query.where(PagamentoRifa.created_at >= data_inicio)

    if data_fim_str:
        data_fim = datetime.strptime(data_fim_str, "%Y-%m-%d")
        data_fim = data_fim.replace(hour=23, minute=59, second=59)
        query = query.where(PagamentoRifa.created_at <= data_fim)

    pagamentos = db.session.execute(
        query.order_by(PagamentoRifa.created_at.desc())
    ).scalars().all()

    total_valor = sum(float(p.valor_total) for p in pagamentos if p.status == "pago")
    total_quantidade = sum(p.quantidade_rifas for p in pagamentos)

    # 🔥 base context
    dados = _base_context()

    # 🔥 sobrescreve corretamente (SEM DUPLICIDADE)
    dados["pagamentos"] = pagamentos
    dados["total_valor"] = total_valor
    dados["total_quantidade"] = total_quantidade
    dados["status"] = status
    dados["data_inicio"] = data_inicio_str
    dados["data_fim"] = data_fim_str

    # 🔥 stats
    # 🔥 base filtrada
    pagamentos_filtrados = pagamentos

    # 👤 clientes únicos do filtro
    clientes_unicos = len(set(p.cliente_id for p in pagamentos_filtrados))

    # 💰 total apenas pagos (respeitando filtro)
    total_pago = sum(
        float(p.valor_total) for p in pagamentos_filtrados if p.status == "pago"
    )

    # 📊 total de registros filtrados
    total_pagamentos = len(pagamentos_filtrados)

    dados["stats"] = {
        "clientes": len(set(p.cliente_id for p in pagamentos if p.status == "pago")),
        "pagamentos": len([p for p in pagamentos if p.status == "pago"]),
        "total_pago": sum(
            float(p.valor_total) for p in pagamentos if p.status == "pago"
        )
    }
    return render_template(
        "admin_relatorio_rifas.html",
        **dados
    )

# ✅ CORRIGIDO
@rifas_admin_bp.route("/admin/rifas/cadastro", methods=["GET", "POST"])
@acesso_rifas_required

def admin_rifas_cadastro():
    campanha = None

    if request.method == "POST":
        campanha_id = (request.form.get("campanha_id") or "").strip() or None
        titulo = request.form.get("titulo", "")
        descricao = request.form.get("descricao", "")
        data_sorteio = _parse_date(request.form.get("data_sorteio", ""))
        ativa = request.form.get("ativa") == "on"

        try:
            quantidade_total = int(request.form.get("quantidade_total", "0"))
            valor_rifa = float((request.form.get("valor_rifa", "0") or "0").replace(",", "."))

            campanha = create_or_update_campaign(
                campanha_id=campanha_id,
                titulo=titulo,
                descricao=descricao,
                data_sorteio=data_sorteio,
                valor_rifa=valor_rifa,
                quantidade_total=quantidade_total,
                ativa=ativa,
            )

            db.session.commit()  # ✅ ESSENCIAL

            flash("Campanha de rifa salva com sucesso.", "success")

            return redirect(url_for("rifas_admin.admin_rifas_cadastro", campanha_id=campanha.id))

        except (ValueError, RifaError) as exc:
            db.session.rollback()  # ✅ ESSENCIAL
            flash(str(exc), "danger")

    dados = _base_context()
    campanha_id = request.args.get("campanha_id")

    if campanha_id:
        campanha = get_campaign(campanha_id)

    dados["campanha_form"] = campanha or dados.get("campanha_ativa")

    return render_template("admin_rifa_cadastro.html", **dados)


@rifas_admin_bp.route("/admin/rifas/equipes-vendedores", methods=["GET", "POST"])
@acesso_rifas_required
def admin_equipes_vendedores():

    if request.method == "POST":
        acao = (request.form.get("acao") or "").strip()

        try:
            if acao == "criar_equipe":
                create_team(
                    nome=request.form.get("nome_equipe", ""),
                    ativa=request.form.get("ativa") == "on",
                )
                db.session.commit()
                flash("Equipe cadastrada com sucesso.", "success")

            elif acao == "criar_vendedor":
                create_vendor(
                    nome=request.form.get("nome_vendedor", ""),
                    codigo=request.form.get("codigo_vendedor", ""),
                    equipe_id=request.form.get("equipe_id", ""),
                )
                db.session.commit()
                flash("Vendedor cadastrado com sucesso.", "success")

            elif acao == "editar_equipe":
                update_team(
                    equipe_id=request.form.get("equipe_id"),
                    nome=request.form.get("nome_equipe"),
                    ativa=request.form.get("ativa") == "on"
                )
                db.session.commit()
                flash("Equipe atualizada", "success")

            elif acao == "excluir_equipe":
                delete_team(request.form.get("equipe_id"))
                db.session.commit()
                flash("Equipe excluída", "success")

            elif acao == "editar_vendedor":
                update_vendor(
                    vendedor_id=request.form.get("vendedor_id"),
                    nome=request.form.get("nome_vendedor"),
                    codigo=request.form.get("codigo_vendedor"),
                    equipe_id=request.form.get("equipe_id"),
                )
                db.session.commit()
                flash("Vendedor atualizado", "success")

            elif acao == "excluir_vendedor":
                delete_vendor(request.form.get("vendedor_id"))
                db.session.commit()
                flash("Vendedor excluído", "success")

            else:
                flash("Acao invalida.", "danger")

        except RifaError as exc:
            db.session.rollback()
            flash(str(exc), "danger")

        return redirect(url_for("rifas_admin.admin_equipes_vendedores"))

    # 🔽 GET (TEM QUE FICAR FORA DO POST!)
    dados = _base_context()

    equipes = db.session.execute(
        db.select(Equipe).order_by(Equipe.nome.asc())
    ).scalars().all()

    vendedores = db.session.execute(
        db.select(Vendedor).order_by(Vendedor.nome.asc(), Vendedor.codigo.asc())
    ).scalars().all()

    vendedores_view = []
    for vendedor in vendedores:
        link_relativo = generate_vendor_link(vendedor.codigo)
        link_absoluto = build_public_url("rifas_public.rifas_home", ref=vendedor.codigo)

        vendedores_view.append({
            "id": vendedor.id,
            "nome": vendedor.nome,
            "codigo": vendedor.codigo,
            "equipe_id": vendedor.equipe_id,
            "equipe_nome": vendedor.equipe.nome if vendedor.equipe else "-",
            "link_relativo": link_relativo,
            "link_absoluto": link_absoluto,
        })

    dados["equipes_lista"] = equipes
    dados["vendedores_lista"] = vendedores_view

    return render_template("admin_equipes_vendedores.html", **dados)


@rifas_admin_bp.route("/admin/rifas/resumo.json", methods=["GET"])
@acesso_rifas_required

def admin_rifas_resumo():
    try:
        dados = admin_dashboard_data()
        return jsonify(dados["stats"])
    except RifaSchemaMissingError as exc:
        return jsonify({"erro": str(exc)}), 503
    

@acesso_rifas_required

def admin_pagamento_cancelar(payment_id):
    try:
        cancelar_pagamento(pagamento_id=payment_id)
        db.session.commit()
        flash("Pagamento cancelado com sucesso.", "success")
    except RifaError as exc:
        db.session.rollback()
        flash(str(exc), "danger")

    return redirect(url_for("rifas_admin.admin_pagamento_detalhe", payment_id=payment_id))

from models import PagamentoRifa

@rifas_admin_bp.route("/admin/pagamentos/<payment_id>/cancelar", methods=["POST"])
@acesso_rifas_required

def admin_pagamento_cancelar(payment_id):
    try:
        pagamento = db.session.get(PagamentoRifa, payment_id)

        if not pagamento:
            flash("Pagamento não encontrado.", "danger")
            return redirect(url_for("rifas_admin.admin_pagamentos"))

        if pagamento.status == "cancelado":
            flash("Pagamento já está cancelado.", "warning")
            return redirect(url_for("rifas_admin.admin_pagamento_detalhe", payment_id=payment_id))

        #if pagamento.status == "pago":
            #flash("Não é permitido cancelar pagamento já confirmado.", "danger")
            #return redirect(url_for("rifas_admin.admin_pagamento_detalhe", payment_id=payment_id))

        # 🔥 LIBERA AS RIFAS
        for rifa in pagamento.rifas:
            rifa.status = "disponivel"
            rifa.pagamento_id = None
            rifa.cliente_id = None

        pagamento.status = "cancelado"

        db.session.commit()

        flash("Pagamento cancelado com sucesso.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao cancelar: {str(e)}", "danger")

    return redirect(url_for("rifas_admin.admin_pagamento_detalhe", payment_id=payment_id))

@rifas_admin_bp.route("/admin/limpeza-completa", methods=["POST"])
@acesso_rifas_required

def limpeza_completa():
    from rifas.services import limpeza_completa_rifas

    try:
        resultado = limpeza_completa_rifas()
        db.session.commit()

        flash(
            f"🧹 Limpeza concluída: "
            f"{resultado['pagamentos']} pagamentos e "
            f"{resultado['clientes']} clientes removidos.",
            "success"
        )

    except Exception as e:
        db.session.rollback()
        flash(f"Erro na limpeza: {str(e)}", "danger")

    return redirect(url_for("rifas_admin.admin_pagamentos"))


@rifas_admin_bp.route("/admin/limpeza-preview", methods=["GET"])
@acesso_rifas_required

def limpeza_preview():
    from rifas.services import preview_limpeza_rifas

    dados = preview_limpeza_rifas()
    return jsonify(dados)



CODIGO_SECRETARIA = "paroquia2026"  # 🔒 troque depois

@rifas_admin_bp.route("/rifas/acesso", methods=["GET", "POST"])
def acesso_rifas_secretaria():
    if current_user.is_authenticated and current_user.is_admin():
        session["acesso_rifas"] = True
        session["perfil"] = "admin"
        return redirect(url_for("rifas_admin.admin_rifas"))

    codigo = (request.args.get("codigo") or request.form.get("codigo") or "").strip()
    login_input = (request.form.get("login") or "").strip()
    senha = request.form.get("senha") or ""

    if codigo:
        if codigo == CODIGO_SECRETARIA:
            session["acesso_rifas"] = True
            session["perfil"] = "secretaria"
            return redirect(url_for("rifas_admin.admin_rifas"))

        flash("Código inválido.", "danger")

    if login_input and senha:
        login_limpo = (
            login_input
            .replace(".", "")
            .replace("-", "")
            .replace("(", "")
            .replace(")", "")
            .replace(" ", "")
        )

        usuario = Ministro.query.filter(
            (Ministro.email == login_input)
            | (Ministro.cpf == login_limpo)
            | (Ministro.telefone == login_limpo)
        ).first()

        if usuario and usuario.pode_logar and usuario.check_senha(senha) and usuario.is_admin():
            login_user(usuario)
            session["acesso_rifas"] = True
            session["perfil"] = "admin"
            return redirect(url_for("rifas_admin.admin_rifas"))

        flash("Login admin inválido para acesso às rifas.", "danger")

    return render_template("acesso_rifas.html")    
