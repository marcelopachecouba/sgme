from datetime import date, timedelta

from flask import Blueprint, jsonify, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from services.relatorio_service import obter_saudacao

from models import Escala, Missa, Ministro, Paroquia, Substituicao
from services.dashboard_service import construir_dashboard
from services.escala_imagem_service import gerar_imagem_escala_missa
from services.firebase_service import enviar_push
from services.substituicao_dashboard_service import (
    buscar_ministros_disponiveis,
    buscar_ministros_troca,
    excluir_substituicao_pendente,
    processar_resposta_substituicao,
    serializar_escalados_missa,
    solicitar_substituicao,
    solicitar_troca,
)
from services.whatsapp_service import gerar_link_whatsapp_telefone, montar_mensagem_lembrete
from utils.auth import admin_required


dashboard_bp = Blueprint("dashboard", __name__)


def _escala_missa_da_paroquia(missa_id):
    missa = Missa.query.filter_by(
        id=missa_id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()
    escalas = Escala.query.filter_by(
        id_missa=missa.id,
        id_paroquia=current_user.id_paroquia
    ).all()
    return missa, escalas


def _serializar_estado_substituicao(missa, ministro_original_id):
    dados = buscar_ministros_disponiveis(missa, ministro_original_id)
    return {
        "missa_id": missa.id,
        "escalados": dados["escalados"],
        "disponiveis": dados["disponiveis"],
        "solicitacoes": dados["solicitacoes"],
    }


def _serializar_estado_troca(missa, ministro_original_id):
    dados = buscar_ministros_troca(missa, ministro_original_id)
    return {
        "missa_id": missa.id,
        "trocas": dados["trocas"],
        "solicitacoes": dados["solicitacoes"],
    }


def _pode_gerir_substituicao(ministro_original_id):
    return current_user.is_admin() or current_user.id == ministro_original_id


def _usuario_pode_responder_substituicao(substituicao):
    return True


@dashboard_bp.route("/")
@login_required
def home():
    if not current_user.is_admin():
        return redirect(url_for("escala.dashboard_ministros"))

    hoje = date.today()
    dados = construir_dashboard(
        id_paroquia=current_user.id_paroquia,
        inicio=hoje,
        fim=hoje + timedelta(days=7),
    )
    return render_template("dashboard.html", **dados)


@dashboard_bp.route("/dashboard/avisar_missa/<int:missa_id>", methods=["POST"])
@login_required
@admin_required
def avisar_missa(missa_id):
    missa, escalas = _escala_missa_da_paroquia(missa_id)

    enviados = 0
    sem_token = 0
    nomes_enviados = []
    nomes_sem_token = []
    ids = set()

    for escala in escalas:
        ministro = escala.ministro
        if not ministro or ministro.id in ids:
            continue
        ids.add(ministro.id)

        if not ministro.firebase_token:
            sem_token += 1
            nomes_sem_token.append(ministro.nome)
            continue

        mensagem = montar_mensagem_lembrete(ministro, missa, escala=escala)
        enviar_push(
            ministro.firebase_token,
            "Lembrete de Escala",
            mensagem
        )
        enviados += 1
        nomes_enviados.append(ministro.nome)

    flash(f"Aviso enviado via Firebase para {enviados} ministro(s). {sem_token} sem token ativo.")
    if nomes_enviados:
        flash("Receberam push: " + ", ".join(nomes_enviados))
    if nomes_sem_token:
        flash("Sem token ativo: " + ", ".join(nomes_sem_token))

    return redirect(url_for("dashboard.home"))


@dashboard_bp.route("/dashboard/sem_token/<int:missa_id>")
@login_required
@admin_required
def sem_token_missa(missa_id):
    missa, escalas = _escala_missa_da_paroquia(missa_id)

    sem_token = []
    ids = set()
    for escala in escalas:
        ministro = escala.ministro
        if not ministro or ministro.id in ids:
            continue
        ids.add(ministro.id)
        if not ministro.firebase_token:
            link_wpp = None
            if ministro.telefone:
                mensagem = montar_mensagem_lembrete(ministro, missa, escala=escala)
                link_wpp = gerar_link_whatsapp_telefone(ministro.telefone, mensagem)

            sem_token.append({
                "nome": ministro.nome,
                "telefone": ministro.telefone,
                "link_wpp": link_wpp,
            })

    return render_template(
        "dashboard_sem_token.html",
        missa=missa,
        ministros=sem_token
    )


@dashboard_bp.route("/dashboard/whatsapp_sem_token/<int:missa_id>")
@login_required
@admin_required
def whatsapp_sem_token_missa(missa_id):
    missa, escalas = _escala_missa_da_paroquia(missa_id)

    links = []
    ids = set()
    for escala in escalas:
        ministro = escala.ministro
        if not ministro or ministro.id in ids:
            continue
        ids.add(ministro.id)

        if not ministro.telefone:
            continue

        mensagem = montar_mensagem_lembrete(ministro, missa, escala=escala)
        links.append({
            "nome": ministro.nome,
            "link": gerar_link_whatsapp_telefone(ministro.telefone, mensagem)
        })

    if not links:
        flash("Nenhum ministro com telefone cadastrado para esta missa.")
        return redirect(url_for("dashboard.home"))

    return render_template("whatsapp_lista.html", links=links)


@dashboard_bp.route("/dashboard/escala_imagem/<int:missa_id>.png")
@login_required
@admin_required
def escala_imagem_missa(missa_id):
    missa, escalas = _escala_missa_da_paroquia(missa_id)
    paroquia = Paroquia.query.filter_by(id=current_user.id_paroquia).first()
    nome_paroquia = getattr(paroquia, "nome", "") if paroquia else ""

    arquivo = gerar_imagem_escala_missa(
        missa=missa,
        escalas=escalas,
        nome_paroquia=nome_paroquia,
    )
    nome_arquivo = f"escala-missa-{missa.data.strftime('%Y%m%d')}-{(missa.horario or 'sem-horario').replace(':', 'h')}.png"
    return send_file(arquivo, mimetype="image/png", download_name=nome_arquivo, as_attachment=False)


@dashboard_bp.route("/buscar_ministros_disponiveis")
@login_required
def buscar_ministros_disponiveis_route():
    missa_id = request.args.get("missa_id", type=int)
    ministro_original_id = request.args.get("ministro_original_id", type=int)

    missa = Missa.query.filter_by(
        id=missa_id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()
    ministro_original = Ministro.query.filter_by(
        id=ministro_original_id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()
    if not _pode_gerir_substituicao(ministro_original.id):
        return jsonify({"ok": False, "mensagem": "Sem permissao para esta substituicao."}), 403

    dados = _serializar_estado_substituicao(missa, ministro_original.id)
    dados["ministro_original"] = {
        "id": ministro_original.id,
        "nome": ministro_original.nome,
        "comunidade": ministro_original.comunidade or "-",
    }
    return jsonify(dados)


@dashboard_bp.route("/buscar_ministros_troca")
@login_required
def buscar_ministros_troca_route():
    missa_id = request.args.get("missa_id", type=int)
    ministro_original_id = request.args.get("ministro_original_id", type=int)

    missa = Missa.query.filter_by(
        id=missa_id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()
    ministro_original = Ministro.query.filter_by(
        id=ministro_original_id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()
    if not _pode_gerir_substituicao(ministro_original.id):
        return jsonify({"ok": False, "mensagem": "Sem permissao para esta troca."}), 403

    dados = _serializar_estado_troca(missa, ministro_original.id)
    dados["ministro_original"] = {
        "id": ministro_original.id,
        "nome": ministro_original.nome,
        "comunidade": ministro_original.comunidade or "-",
    }
    return jsonify(dados)


@dashboard_bp.route("/solicitar_substituicao", methods=["POST"])
@login_required
def solicitar_substituicao_route():
    payload = request.get_json(silent=True) or request.form
    missa_id = int(payload.get("missa_id"))
    ministro_original_id = int(payload.get("ministro_original_id"))
    ministro_substituto_id = int(payload.get("ministro_substituto_id"))

    missa = Missa.query.filter_by(
        id=missa_id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()
    ministro_original = Ministro.query.filter_by(
        id=ministro_original_id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()
    if not _pode_gerir_substituicao(ministro_original.id):
        return jsonify({"ok": False, "mensagem": "Sem permissao para esta substituicao."}), 403
    ministro_substituto = Ministro.query.filter_by(
        id=ministro_substituto_id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()

    dados_disponibilidade = buscar_ministros_disponiveis(missa, ministro_original.id)
    if ministro_substituto.id not in {item["id"] for item in dados_disponibilidade["disponiveis"]}:
        return jsonify({"ok": False, "mensagem": "Ministro nao esta disponivel para esta substituicao."}), 400

    substituicao, whatsapp_link, criada = solicitar_substituicao(
        missa,
        ministro_original,
        ministro_substituto,
    )

    return jsonify({
        "ok": True,
        "criada": criada,
        "mensagem": (
            f"Solicitacao enviada para {ministro_substituto.nome}."
            if criada else
            f"Ja existe solicitacao pendente para {ministro_substituto.nome}."
        ),
        "substituicao": {
            "id": substituicao.id,
            "status": substituicao.status,
        },
        "whatsapp_link": whatsapp_link,
        "estado": _serializar_estado_substituicao(missa, ministro_original.id),
    })


@dashboard_bp.route("/solicitar_troca", methods=["POST"])
@login_required
def solicitar_troca_route():
    payload = request.get_json(silent=True) or request.form
    missa_id = int(payload.get("missa_id"))
    ministro_original_id = int(payload.get("ministro_original_id"))
    missa_troca_id = int(payload.get("missa_troca_id"))
    ministro_troca_id = int(payload.get("ministro_troca_id"))

    missa = Missa.query.filter_by(
        id=missa_id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()
    missa_troca = Missa.query.filter_by(
        id=missa_troca_id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()
    ministro_original = Ministro.query.filter_by(
        id=ministro_original_id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()
    if not _pode_gerir_substituicao(ministro_original.id):
        return jsonify({"ok": False, "mensagem": "Sem permissao para esta troca."}), 403
    ministro_troca = Ministro.query.filter_by(
        id=ministro_troca_id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()

    dados_troca = buscar_ministros_troca(missa, ministro_original.id)
    if (missa_troca.id, ministro_troca.id) not in {
        (item["missa_id"], item["ministro_id"])
        for item in dados_troca["trocas"]
    }:
        return jsonify({"ok": False, "mensagem": "Ministro nao esta disponivel para esta troca."}), 400

    substituicao, whatsapp_link, criada = solicitar_troca(
        missa,
        ministro_original,
        missa_troca,
        ministro_troca,
    )

    return jsonify({
        "ok": True,
        "criada": criada,
        "mensagem": (
            f"Solicitacao de troca enviada para {ministro_troca.nome}."
            if criada else
            f"Ja existe solicitacao pendente de troca para {ministro_troca.nome}."
        ),
        "substituicao": {
            "id": substituicao.id,
            "status": substituicao.status,
            "tipo": substituicao.tipo,
        },
        "whatsapp_link": whatsapp_link,
        "estado": _serializar_estado_troca(missa, ministro_original.id),
    })


@dashboard_bp.route("/excluir_substituicao", methods=["POST"])
@login_required
def excluir_substituicao_route():
    payload = request.get_json(silent=True) or request.form
    substituicao_id = int(payload.get("substituicao_id"))

    substituicao = Substituicao.query.filter_by(id=substituicao_id).first_or_404()
    missa = Missa.query.filter_by(
        id=substituicao.missa_id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()
    if not _pode_gerir_substituicao(substituicao.ministro_original_id):
        return jsonify({"ok": False, "mensagem": "Sem permissao para esta substituicao."}), 403

    ok, mensagem = excluir_substituicao_pendente(substituicao)
    status_code = 200 if ok else 400
    return jsonify({
        "ok": ok,
        "mensagem": mensagem,
        "estado": _serializar_estado_substituicao(missa, substituicao.ministro_original_id),
    }), status_code

import routes.auth_routes as auth

@dashboard_bp.route("/responder_substituicao", methods=["GET", "POST"])
def responder_substituicao():
    substituicao = Substituicao.query.get_or_404(id)

    saudacao = obter_saudacao()

    if request.method == "POST":
        payload = request.get_json(silent=True) or request.form
        substituicao_id = int(payload.get("substituicao_id"))
        acao = (payload.get("acao") or "").strip().lower()
    else:
        substituicao_id = request.args.get("substituicao_id", type=int)
        acao = (request.args.get("acao") or "").strip().lower()

    substituicao = Substituicao.query.filter_by(id=substituicao_id).first_or_404()

    if not _usuario_pode_responder_substituicao(substituicao):
        mensagem = "Voce nao pode responder esta solicitacao."
        if request.method == "POST":
            return jsonify({"ok": False, "mensagem": mensagem}), 403
        return render_template("substituicao_publica_resultado.html", sucesso=False, mensagem=mensagem), 403

    if not acao:
        return render_template(
            "responder_substituicao.html",
            substituicao=substituicao,
            acao_sugerida="",
        )

    if request.method == "GET":
        return render_template(
            "responder_substituicao.html",
            substituicao=substituicao,
            acao_sugerida=acao,
        )

    sucesso, mensagem = processar_resposta_substituicao(substituicao, acao)
    paroquia_id = substituicao.missa.id_paroquia if substituicao.missa else None
    escala_atual = Escala.query.filter_by(
        id_missa=substituicao.missa_id,
        id_paroquia=paroquia_id,
    ).all()
    resposta = {
        "ok": sucesso,
        "mensagem": mensagem,
        "missa_id": substituicao.missa_id,
        "escalados": serializar_escalados_missa(
            substituicao.missa_id,
            paroquia_id,
        ) if escala_atual else [],
    }

    if request.method == "POST":
        status_code = 200 if sucesso else 400
        return jsonify(resposta), status_code

    return render_template(
        "substituicao_publica_resultado.html",
        sucesso=sucesso,
        mensagem=mensagem,
    )
