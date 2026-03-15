
import random
import math
import calendar
from collections import defaultdict
from datetime import datetime, date
from flask import Blueprint, render_template, redirect, request, url_for, flash, send_file
from flask_login import login_required, current_user
from models import (
    db,
    Ministro,
    Missa,
    Escala,
    EscalaFixa,
    Presenca,
    Disponibilidade,
    DisponibilidadeFixa,
    Indisponibilidade,
    IndisponibilidadeFixa,
    PedidoSubstituicao,
    PresencaReuniao,
    ReuniaoFormacao,
)
from datetime import timedelta
import uuid, urllib.parse, base64, io
from utils.auth import admin_required
from services.notificacao_service import (
    notificar_escala_criada,
    notificar_escala_removida
)
from services.disponibilidade_service import esta_indisponivel, esta_disponivel
from services.participacao_service import (
    obter_estatisticas_participacao,
    obter_missas_ministro_periodo,
)

from services.substituicao_service import substituir_ministro
from services.firebase_service import enviar_push
from services.pedido_substituicao_service import (
    aceitar_substituicao,
    criar_pedido_substituicao,
    excluir_pedidos_substituicao_da_escala,
)
from services.paroquia_scope_service import (
    get_escala_fixa_or_404,
    get_escala_or_404,
    get_ministro_or_404,
    get_missa_or_404,
)

escala_bp = Blueprint("escala", __name__)

@escala_bp.route("/escala/<int:missa_id>", methods=["GET", "POST"])
@login_required
@admin_required
def gerar_escala(missa_id):

    missa = get_missa_or_404(missa_id, current_user.id_paroquia)
    ministros = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).all()

    if request.method == "POST":
        selecionados = request.form.getlist("ministros")
        Escala.query.filter_by(id_missa=missa.id).delete()
        ministros_indisponiveis = []

        for ministro_id in selecionados:
            ministro = Ministro.query.filter_by(
                id=ministro_id,
                id_paroquia=current_user.id_paroquia
            ).first()
            if not ministro:
                continue
            if esta_indisponivel(ministro.id, missa, current_user.id_paroquia):
                ministros_indisponiveis.append(ministro.nome)
                continue
            nova = Escala(
                id_missa=missa.id,
                id_ministro=int(ministro_id),
                id_paroquia=current_user.id_paroquia,
                token=str(uuid.uuid4())
            )
            db.session.add(nova)
            missa.escala_ref = nova
            notificar_escala_criada(ministro, missa)

        db.session.commit()
        if ministros_indisponiveis:
            flash(
                "Nao foi possivel escalar manualmente os ministros indisponiveis: "
                + ", ".join(sorted(ministros_indisponiveis))
            )

        return redirect(url_for("escala.visualizar_escala", missa_id=missa.id))

    return render_template("gerar_escala.html", missa=missa, ministros=ministros)

# ======================
# ESCALA AUTOMÁTICA
# ======================

from utils.auth import admin_required
@escala_bp.route("/escala/auto/<int:missa_id>", methods=["POST"])
@login_required
@admin_required
def gerar_escala_auto(missa_id):

    from services.escala_inteligente_service import selecionar_ministros

    missa = get_missa_or_404(missa_id, current_user.id_paroquia)

    # Limpa escala anterior
    Escala.query.filter_by(id_missa=missa.id).delete()

    selecionados = []

    # ===============================
    # 1️⃣ ESCALA FIXA
    # ===============================

    semana = (missa.data.day - 1) // 7 + 1
    dia_semana = missa.data.weekday()

    fixos = EscalaFixa.query.filter(
        EscalaFixa.id_paroquia == current_user.id_paroquia,
        (EscalaFixa.semana == semana) | (EscalaFixa.semana == None),
        (EscalaFixa.dia_semana == dia_semana) | (EscalaFixa.dia_semana == None),
        (EscalaFixa.horario == missa.horario) | (EscalaFixa.horario == None),
        (EscalaFixa.comunidade == missa.comunidade) | (EscalaFixa.comunidade == None)
    ).all()

    for fixa in fixos:

        ministro = Ministro.query.filter_by(
            id=fixa.id_ministro,
            id_paroquia=current_user.id_paroquia
        ).first()

        if not ministro:
            continue

        conflito_dia = db.session.query(Escala)\
            .join(Missa)\
            .filter(
                Escala.id_ministro == ministro.id,
                Escala.id_paroquia == current_user.id_paroquia,
                Missa.data == missa.data,
            ).first()

        if conflito_dia:
            continue

        # verifica indisponibilidade
        if esta_indisponivel(ministro.id, missa, current_user.id_paroquia):
            continue

        # verifica disponibilidade (fixa ou por data)
        if not esta_disponivel(ministro.id, missa, current_user.id_paroquia):
            continue
        
        if ministro not in selecionados:
            selecionados.append(ministro)

        if len(selecionados) >= missa.qtd_ministros:
            break


    # ===============================
    # 2️⃣ ESCALA INTELIGENTE
    # ===============================

    if len(selecionados) < missa.qtd_ministros:

        restantes = missa.qtd_ministros - len(selecionados)

        candidatos = selecionar_ministros(
            restantes,
            current_user.id_paroquia,
            missa
        )

        for ministro in candidatos:

            if ministro in selecionados:
                continue

            # conflito de horário
            conflito = db.session.query(Escala)\
                .join(Missa)\
                .filter(
                    Escala.id_ministro == ministro.id,
                    Missa.data == missa.data,
                    Escala.id_paroquia == current_user.id_paroquia
                ).first()

            if conflito:
                continue

            if esta_indisponivel(ministro.id, missa, current_user.id_paroquia):
                continue

            if not esta_disponivel(ministro.id, missa, current_user.id_paroquia):
                continue

            selecionados.append(ministro)

            if len(selecionados) >= missa.qtd_ministros:
                break


    # ===============================
    # 3️⃣ SALVAR ESCALA
    # ===============================

    for ministro in selecionados:

        nova = Escala(
            id_missa=missa.id,
            id_ministro=ministro.id,
            id_paroquia=current_user.id_paroquia,
            token=str(uuid.uuid4())
        )

        db.session.add(nova)
        missa.escala_ref = nova
        notificar_escala_criada(ministro, missa)

    db.session.commit()

    flash("Escala automática gerada com sucesso!")

    return redirect(url_for("escala.visualizar_escala", missa_id=missa.id))


@escala_bp.route("/escala/auto_inteligente/<int:missa_id>", methods=["GET", "POST"])
@login_required
@admin_required
def gerar_escala_auto_inteligente(missa_id):
    from services.escala_inteligente_service import selecionar_ministros

    missa = get_missa_or_404(missa_id, current_user.id_paroquia)

    if request.method == "GET":
        return render_template("form_escala_auto_inteligente_missa.html", missa=missa)

    Escala.query.filter_by(
        id_missa=missa.id,
        id_paroquia=current_user.id_paroquia
    ).delete(synchronize_session=False)

    considerar_periodos_anteriores = bool(
        request.form.get("considerar_periodos_anteriores")
    )
    opcoes_geracao = _normalizar_opcoes_geracao(
        request.form.getlist("ordem_geracao")
    )

    selecionados = selecionar_ministros(
        missa.qtd_ministros,
        current_user.id_paroquia,
        missa,
        considerar_periodos_anteriores=considerar_periodos_anteriores,
        modo_ordenacao=opcoes_geracao
    )

    for ministro in selecionados:
        nova = Escala(
            id_missa=missa.id,
            id_ministro=ministro.id,
            id_paroquia=current_user.id_paroquia,
            token=str(uuid.uuid4())
        )
        db.session.add(nova)
        missa.escala_ref = nova
        notificar_escala_criada(ministro, missa)

    db.session.commit()
    flash("Escala auto inteligente gerada com sucesso!")
    return redirect(url_for("escala.visualizar_escala", missa_id=missa.id))


from sqlalchemy import extract, func

@escala_bp.route("/escala/visualizar/<int:missa_id>")
@login_required
def visualizar_escala(missa_id):

    missa = get_missa_or_404(missa_id, current_user.id_paroquia)

    escalas = Escala.query.filter_by(
        id_missa=missa.id,
        id_paroquia=current_user.id_paroquia
    ).all()

    # ministros já escalados no mesmo dia
    ministros_ocupados = db.session.query(Escala.id_ministro)\
        .join(Missa)\
        .filter(
            Escala.id_paroquia == current_user.id_paroquia,
            Missa.data == missa.data
        ).subquery()

    # todos disponíveis
    ministros = Ministro.query.filter(
        Ministro.id_paroquia == current_user.id_paroquia,
        ~Ministro.id.in_(ministros_ocupados)
    ).all()

    # remove indisponíveis
    ministros = [
        m for m in ministros
        if not esta_indisponivel(m.id, missa, current_user.id_paroquia)
    ]

    # contar missas no mês
    contagem = dict(
        db.session.query(
            Escala.id_ministro,
            func.count(Escala.id)
        )
        .join(Missa)
        .filter(
            Escala.id_paroquia == current_user.id_paroquia,
            extract("month", Missa.data) == missa.data.month,
            extract("year", Missa.data) == missa.data.year
        )
        .group_by(Escala.id_ministro)
        .all()
    )

    # ordenar por menos missas
    ministros.sort(key=lambda m: contagem.get(m.id, 0))

    return render_template(
        "visualizar_escala.html",
        missa=missa,
        escalas=escalas,
        ministros=ministros,
        contagem=contagem
    )


from utils.auth import admin_required
@escala_bp.route("/escala_fixa", methods=["GET", "POST"])
@login_required
@admin_required
def escala_fixa():

    ministros = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Ministro.nome).all()

    if request.method == "POST":

        semana = request.form.get("semana")
        dia_semana = request.form.get("dia_semana")
        horario = request.form.get("horario")
        comunidade = request.form.get("comunidade")

        ministros_ids = request.form.getlist("ministros")

        if not ministros_ids:
            flash("Selecione pelo menos um ministro.")
            return redirect(url_for("escala.escala_fixa"))

        for ministro_id in ministros_ids:
            ministro = Ministro.query.filter_by(
                id=ministro_id,
                id_paroquia=current_user.id_paroquia
            ).first()
            if not ministro:
                continue

            nova = EscalaFixa(
                semana=int(semana) if semana else None,
                dia_semana=int(dia_semana) if dia_semana else None,
                horario=horario if horario else None,
                comunidade=comunidade if comunidade else None,
                id_ministro=ministro.id,
                id_paroquia=current_user.id_paroquia
            )

            db.session.add(nova)

        db.session.commit()

        flash("Escala fixa cadastrada com sucesso!")
        return redirect(url_for("escala.escala_fixa"))

    fixos = EscalaFixa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).all()

    return render_template(
        "escala_fixa.html",
        ministros=ministros,
        fixos=fixos
    )


@escala_bp.route("/escala_fixa/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_escala_fixa(id):

    fixa = get_escala_fixa_or_404(id, current_user.id_paroquia)

    ministros = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Ministro.nome).all()

    if request.method == "POST":

        fixa.semana = int(request.form["semana"]) if request.form.get("semana") else None
        fixa.dia_semana = int(request.form["dia_semana"]) if request.form.get("dia_semana") else None
        fixa.horario = request.form.get("horario") or None
        fixa.comunidade = request.form.get("comunidade") or None

        db.session.commit()

        flash("Escala fixa atualizada com sucesso!")
        return redirect(url_for("escala.escala_fixa"))

    return render_template(
        "editar_escala_fixa.html",
        fixa=fixa,
        ministros=ministros
    )

from utils.auth import admin_required
@escala_bp.route("/escala_fixa/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_escala_fixa(id):

    fixa = get_escala_fixa_or_404(id, current_user.id_paroquia)
    db.session.delete(fixa)
    db.session.commit()

    flash("Escala fixa removida.")
    return redirect(url_for("escala.escala_fixa"))


@escala_bp.route("/escala_mensal", methods=["GET", "POST"])
@login_required
@admin_required
def escala_mensal():

    if request.method == "POST":

        mes = int(request.form["mes"])
        ano = int(request.form["ano"])

        inicio_mes = date(ano, mes, 1)
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        fim_mes = date(ano, mes, ultimo_dia)

        domingos = []
        dia = inicio_mes

        # =============================
        # BUSCA TODOS OS DOMINGOS
        # =============================
        while dia <= fim_mes:
            if dia.weekday() == 6:  # 6 = Domingo
                domingos.append(dia)
            dia += timedelta(days=1)

        estrutura = {}

        # =============================
        # MONTA ESTRUTURA
        # =============================
        for domingo in domingos:

            semana = (domingo.day - 1) // 7 + 1

            estrutura[semana] = {
                "data": domingo,
                "manha": [],
                "noite": []
            }

            missas = Missa.query.filter_by(
                data=domingo,
                id_paroquia=current_user.id_paroquia
            ).all()

            for missa in missas:

                escalas = Escala.query.filter_by(
                    id_missa=missa.id
                ).all()

                nomes = [e.ministro.nome for e in escalas]

                # Se horário começa com 08 ou contém 8 → manhã
                if "8" in missa.horario or "07" in missa.horario:
                    estrutura[semana]["manha"] = nomes
                else:
                    estrutura[semana]["noite"] = nomes

        return render_template(
            "escala_mensal_editavel.html",
            estrutura=estrutura,
            mes=mes,
            ano=ano
        )

    return render_template("form_escala_mensal.html")



@escala_bp.route("/escala_fixa/visao")
@login_required
def visao_escala_fixa():

    fixos = EscalaFixa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).all()

    estrutura = {}

    for f in fixos:

        if not f.ministro:
            continue

        semana = f.semana if f.semana else 0
        dia = f.dia_semana if f.dia_semana is not None else -1
        horario = f.horario if f.horario else "99:99"

        if semana not in estrutura:
            estrutura[semana] = {}

        if dia not in estrutura[semana]:
            estrutura[semana][dia] = {}

        if horario not in estrutura[semana][dia]:
            estrutura[semana][dia][horario] = set()  # 🔥 AQUI MUDOU

        estrutura[semana][dia][horario].add(f.ministro.nome)  # 🔥 AQUI MUDOU

    # Converter set para lista ordenada
    for semana in estrutura:
        for dia in estrutura[semana]:
            for horario in estrutura[semana][dia]:
                estrutura[semana][dia][horario] = sorted(
                    list(estrutura[semana][dia][horario])
                )

    return render_template(
        "visao_escala_fixa.html",
        estrutura=estrutura
    )

from utils.auth import admin_required
@escala_bp.route("/gerar_mensal", methods=["GET", "POST"])
@login_required
@admin_required
def gerar_mensal():
    flash("Geracao unificada: use Gerar Escala Inteligente.")
    return redirect(url_for("escala.gerar_escala_inteligente"))


@escala_bp.route("/gerar_mensal_inteligente", methods=["GET", "POST"])
@login_required
@admin_required
def gerar_mensal_inteligente():
    return gerar_escala_inteligente()

from sqlalchemy import extract


def _normalizar_opcoes_geracao(opcoes):
    if isinstance(opcoes, str):
        opcoes = [opcoes]

    permitidas = {
        "equilibrada",
        "casais_fim_semana",
        "casais_semana",
        "minimo_missas",
        "semana_primeiro",
        "fim_semana_primeiro",
    }
    normalizadas = []

    for opcao in opcoes or []:
        valor = (opcao or "").strip()
        if valor and valor in permitidas and valor not in normalizadas:
            normalizadas.append(valor)

    return normalizadas or ["equilibrada"]


def _ordenar_missas_para_geracao(missas, opcoes_geracao):
    opcoes_geracao = _normalizar_opcoes_geracao(opcoes_geracao)

    if "semana_primeiro" in opcoes_geracao:
        return sorted(missas, key=lambda m: (m.data.weekday() in {5, 6}, m.data, m.horario or "", m.id))
    if "fim_semana_primeiro" in opcoes_geracao:
        return sorted(missas, key=lambda m: (m.data.weekday() not in {5, 6}, m.data, m.horario or "", m.id))
    return sorted(missas, key=lambda m: (m.data.weekday() != 6, m.data, m.horario or "", m.id))

def _executar_geracao_escala_inteligente(mes, ano, considerar_periodos_anteriores, opcoes_geracao):
    from services.escala_inteligente_service import selecionar_ministros

    opcoes_geracao = _normalizar_opcoes_geracao(opcoes_geracao)

    missas_mes_subquery = db.session.query(Missa.id).filter(
        Missa.id_paroquia == current_user.id_paroquia,
        extract("month", Missa.data) == mes,
        extract("year", Missa.data) == ano
    ).subquery()

    Escala.query.filter(
        Escala.id_paroquia == current_user.id_paroquia,
        Escala.id_missa.in_(missas_mes_subquery)
    ).delete(synchronize_session=False)

    missas_mes = Missa.query.filter(
        Missa.id_paroquia == current_user.id_paroquia,
        extract("month", Missa.data) == mes,
        extract("year", Missa.data) == ano
    ).order_by(Missa.data.asc(), Missa.horario.asc(), Missa.id.asc()).all()

    for missa in _ordenar_missas_para_geracao(missas_mes, opcoes_geracao):
        ministros = selecionar_ministros(
            missa.qtd_ministros,
            current_user.id_paroquia,
            missa,
            considerar_periodos_anteriores=considerar_periodos_anteriores,
            modo_ordenacao=opcoes_geracao
        )

        for ministro in ministros:
            nova = Escala(
                id_missa=missa.id,
                id_ministro=ministro.id,
                id_paroquia=current_user.id_paroquia,
                token=str(uuid.uuid4())
            )
            db.session.add(nova)
            missa.escala_ref = nova
            notificar_escala_criada(ministro, missa)

    db.session.commit()


def _enviar_escala_mes_ministros(id_paroquia, mes, ano):
    escalas_mes = Escala.query.join(Missa).filter(
        Escala.id_paroquia == id_paroquia,
        extract("month", Missa.data) == mes,
        extract("year", Missa.data) == ano,
    ).all()

    por_ministro = defaultdict(list)
    for e in escalas_mes:
        if e.ministro:
            por_ministro[e.ministro].append(e)

    enviados = 0
    sem_token = 0
    sem_link_publico = 0

    for ministro, lista in por_ministro.items():
        pendentes = [e for e in lista if e.confirmado is not True]
        if not pendentes:
            continue

        if not ministro.token_publico:
            sem_link_publico += 1
            continue

        link = url_for(
            "escala.pendencias_ministro",
            token_publico=ministro.token_publico,
            mes=mes,
            ano=ano,
            _external=True,
        )

        if ministro.firebase_token:
            enviar_push(
                ministro.firebase_token,
                "Escala do Mes",
                (
                    f"Voce possui {len(pendentes)} escala(s) pendente(s) em {mes}/{ano}. "
                    f"Acesse para confirmar ou recusar: {link}"
                ),
                url=link,
            )
            enviados += 1
        else:
            sem_token += 1

    return {
        "enviados": enviados,
        "sem_token": sem_token,
        "sem_link_publico": sem_link_publico,
    }


def _distancia_metros(lat1, lon1, lat2, lon2):
    raio_terra = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return raio_terra * c


@escala_bp.route("/gerar_escala_inteligente", methods=["GET", "POST"])
@login_required
@admin_required
def gerar_escala_inteligente():
    if request.method == "POST":
        mes = int(request.form["mes"])
        ano = int(request.form["ano"])
        considerar_periodos_anteriores = bool(
            request.form.get("considerar_periodos_anteriores")
        )
        enviar_escala_ministros = bool(
            request.form.get("enviar_escala_ministros")
        )
        opcoes_geracao = _normalizar_opcoes_geracao(
            request.form.getlist("ordem_geracao")
        )

        _executar_geracao_escala_inteligente(
            mes=mes,
            ano=ano,
            considerar_periodos_anteriores=considerar_periodos_anteriores,
            opcoes_geracao=opcoes_geracao
        )

        if enviar_escala_ministros:
            resultado_envio = _enviar_escala_mes_ministros(
                id_paroquia=current_user.id_paroquia,
                mes=mes,
                ano=ano,
            )
            flash(
                f"Envio mensal: {resultado_envio['enviados']} ministro(s) notificado(s), "
                f"{resultado_envio['sem_token']} sem token, "
                f"{resultado_envio['sem_link_publico']} sem link publico."
            )

        flash("Escala inteligente do mes gerada com sucesso!")
        return redirect(url_for("missas.missas"))

    return render_template("form_gerar_escala_inteligente.html")


@escala_bp.route("/gerar_mensal_super_inteligente", methods=["GET", "POST"])
@login_required
@admin_required
def gerar_mensal_super_inteligente():
    return gerar_escala_inteligente()


@escala_bp.route("/escala/pendencias/<token_publico>")
def pendencias_ministro(token_publico):
    ministro = Ministro.query.filter_by(token_publico=token_publico).first_or_404()

    hoje = date.today()
    mes = int(request.args.get("mes", hoje.month))
    ano = int(request.args.get("ano", hoje.year))

    escalas = Escala.query.join(Missa).filter(
        Escala.id_ministro == ministro.id,
        Escala.id_paroquia == ministro.id_paroquia,
        extract("month", Missa.data) == mes,
        extract("year", Missa.data) == ano,
    ).order_by(Missa.data.asc(), Missa.horario.asc()).all()

    return render_template(
        "pendencias_ministro.html",
        ministro=ministro,
        escalas=escalas,
        mes=mes,
        ano=ano,
    )


@escala_bp.route("/substituicao/aceitar/<pedido_token>/<ministro_token_publico>")
def aceitar_substituicao_publica(pedido_token, ministro_token_publico):
    sucesso, mensagem = aceitar_substituicao(pedido_token, ministro_token_publico)
    return render_template(
        "substituicao_publica_resultado.html",
        sucesso=sucesso,
        mensagem=mensagem,
    )
from utils.auth import admin_required
@escala_bp.route("/escala/remover/<int:escala_id>", methods=["POST"])
@login_required
@admin_required
def remover_ministro_escala(escala_id):

    escala = get_escala_or_404(escala_id, current_user.id_paroquia)

    ministro = escala.ministro
    missa = escala.missa
    missa_id = escala.id_missa

    excluir_pedidos_substituicao_da_escala(escala.id, current_user.id_paroquia)
    db.session.delete(escala)
    db.session.commit()

    # 🔔 envia notificação
    notificar_escala_removida(ministro, missa)

    flash("Ministro removido da escala!")
    return redirect(url_for("escala.visualizar_escala", missa_id=missa_id))


@escala_bp.route("/escala/adicionar/<int:missa_id>", methods=["POST"])
@login_required
@admin_required
def adicionar_ministro_escala(missa_id):

    ministro_id = request.form.get("ministro_id")

    if not ministro_id:
        flash("Selecione um ministro.")
        return redirect(url_for("escala.visualizar_escala", missa_id=missa_id))

    missa = get_missa_or_404(missa_id, current_user.id_paroquia)
    ministro = get_ministro_or_404(ministro_id, current_user.id_paroquia)

    existe = Escala.query.filter_by(
        id_missa=missa_id,
        id_ministro=ministro_id
    ).first()

    if existe:
        flash("Este ministro já está na escala.")
        return redirect(url_for("escala.visualizar_escala", missa_id=missa_id))

    nova = Escala(
        id_missa=missa_id,
        id_ministro=ministro_id,
        id_paroquia=current_user.id_paroquia,
        token=str(uuid.uuid4())
    )

    db.session.add(nova)
    db.session.commit()

    flash("Ministro adicionado com sucesso!")

    return redirect(url_for("escala.visualizar_escala", missa_id=missa_id))


@escala_bp.route("/salvar_mensal", methods=["POST"])
@login_required
@admin_required
def salvar_mensal():

    mes = int(request.form["mes"])
    ano = int(request.form["ano"])

    cal = calendar.monthcalendar(ano, mes)

    for semana in cal:
        for dia_semana, dia in enumerate(semana):

            if dia == 0:
                continue

            data_missa = date(ano, mes, dia)
            semana_mes = (dia - 1) // 7 + 1

            regras = EscalaFixa.query.filter_by(
                id_paroquia=current_user.id_paroquia
            ).all()

            for regra in regras:

                if regra.semana and regra.semana != semana_mes:
                    continue

                if regra.dia_semana is not None and regra.dia_semana != dia_semana:
                    continue

                missa = Missa.query.filter_by(
                    data=data_missa,
                    horario=regra.horario,
                    id_paroquia=current_user.id_paroquia
                ).first()

                if not missa:
                    missa = Missa(
                        data=data_missa,
                        horario=regra.horario,
                        comunidade=regra.comunidade or "Matriz",
                        qtd_ministros=1,
                        id_paroquia=current_user.id_paroquia
                    )
                    db.session.add(missa)
                    db.session.commit()

                escala_existente = Escala.query.filter_by(
                    id_missa=missa.id,
                    id_ministro=regra.id_ministro
                ).first()

                if not escala_existente and not esta_indisponivel(
                    regra.id_ministro,
                    missa,
                    current_user.id_paroquia
                ):
                    nova = Escala(
                        id_missa=missa.id,
                        id_ministro=regra.id_ministro,
                        id_paroquia=current_user.id_paroquia,
                        token=str(uuid.uuid4())
                    )
                    db.session.add(nova)

    db.session.commit()

    flash("Escala mensal criada com sucesso!")
    return redirect(url_for("missas.missas"))

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.platypus import Table
from reportlab.lib.pagesizes import A4
from reportlab.platypus import TableStyle
import io
from flask import send_file


@escala_bp.route("/escala/publica/<token>", methods=["GET", "POST"])
def escala_publica(token):

    escala = Escala.query.filter_by(token=token).first_or_404()

    if request.method == "POST":

        acao = request.form.get("acao")

        if acao == "confirmar":
            escala.confirmado = True
            db.session.commit()

            flash("Presença confirmada. Obrigado!")

        elif acao == "recusar":

            missa = escala.missa
            paroquia_id = escala.id_paroquia
            recusada = Escala(
                id=escala.id,
                id_missa=escala.id_missa,
                id_ministro=escala.id_ministro,
                id_paroquia=escala.id_paroquia,
                token=escala.token,
            )
            recusada.missa = missa

            excluir_pedidos_substituicao_da_escala(escala.id, escala.id_paroquia)
            db.session.delete(escala)
            db.session.commit()

            substituido = substituir_ministro(recusada)

            if substituido:
                flash("Voce foi removido da escala. Um substituto foi acionado e notificado.")
            else:
                flash("Voce foi removido da escala, mas nao foi encontrado substituto automatico.")

            return redirect(url_for("publico.calendario_paroquia", id=paroquia_id))

        elif acao == "substituicao":
            pedido, enviados, links_whatsapp = criar_pedido_substituicao(escala)
            if links_whatsapp:
                flash(
                    f"Pedido de substituicao aberto. Push enviados: {enviados}. "
                    "Voce tambem pode avisar pelo WhatsApp."
                )
                return render_template(
                    "whatsapp_lista.html",
                    links=links_whatsapp,
                    titulo="Avisar Substitutos por WhatsApp",
                    mensagem_topo=(
                        "Os links abaixo levam a uma mensagem com o link de confirmacao. "
                        "Quem confirmar primeiro entra automaticamente na escala."
                    ),
                    voltar_url=url_for("escala.escala_publica", token=escala.token),
                )
            flash(
                f"Pedido de substituicao aberto. "
                f"Ministros notificados: {enviados}."
            )
            return redirect(url_for("escala.escala_publica", token=escala.token))

    return render_template(
        "escala_publica.html",
        escala=escala,
        missa=escala.missa,
        ministro=escala.ministro
    )


@escala_bp.route("/checkin/publico/<token>", methods=["GET", "POST"])
def checkin_publico_localizacao(token):
    escala = Escala.query.filter_by(token=token).first_or_404()
    missa = escala.missa
    ministro = escala.ministro

    if request.method == "POST":
        payload = request.get_json(silent=True) or request.form
        latitude = payload.get("latitude")
        longitude = payload.get("longitude")

        if not missa.latitude or not missa.longitude:
            return {"ok": False, "mensagem": "Esta missa nao possui localizacao cadastrada."}, 400

        try:
            lat_usuario = float(latitude)
            lon_usuario = float(longitude)
            lat_missa = float(missa.latitude)
            lon_missa = float(missa.longitude)
        except (TypeError, ValueError):
            return {"ok": False, "mensagem": "Localizacao invalida."}, 400

        distancia = _distancia_metros(lat_usuario, lon_usuario, lat_missa, lon_missa)
        raio_maximo = 300

        if distancia > raio_maximo:
            return {
                "ok": False,
                "mensagem": f"Voce esta a {int(distancia)}m da missa. Aproximacao maxima: {raio_maximo}m.",
            }, 400

        presenca = Presenca.query.filter_by(
            ministro_id=escala.id_ministro,
            id_missa=escala.id_missa
        ).first()

        if not presenca:
            presenca = Presenca(
                ministro_id=escala.id_ministro,
                id_missa=escala.id_missa,
                presente=True,
            )
            db.session.add(presenca)
        else:
            presenca.presente = True

        escala.confirmado = True
        escala.presente = True
        db.session.commit()

        return {"ok": True, "mensagem": "Presenca confirmada com sucesso."}

    return render_template(
        "checkin_publico.html",
        escala=escala,
        missa=missa,
        ministro=ministro,
    )

@escala_bp.route("/dashboard_ministros")
@login_required
def dashboard_ministros():
    inicio_str = (request.args.get("inicio") or "").strip()
    fim_str = (request.args.get("fim") or "").strip()

    data_inicio = datetime.strptime(inicio_str, "%Y-%m-%d").date() if inicio_str else None
    data_fim = datetime.strptime(fim_str, "%Y-%m-%d").date() if fim_str else None
    filtro_ministro_id = None if current_user.is_admin() else current_user.id

    resultado = obter_estatisticas_participacao(
        current_user.id_paroquia,
        data_inicio=data_inicio,
        data_fim=data_fim,
        ministro_id=filtro_ministro_id,
    )

    return render_template(
        "dashboard_ministros.html",
        dados=resultado["dados"],
        resumo=resultado["resumo"],
        inicio=inicio_str,
        fim=fim_str,
        somente_proprio=not current_user.is_admin(),
    )


@escala_bp.route("/dashboard_ministros/ministro/<int:ministro_id>")
@login_required
def dashboard_ministro_detalhe(ministro_id):
    inicio_str = (request.args.get("inicio") or "").strip()
    fim_str = (request.args.get("fim") or "").strip()
    mes_ref = request.args.get("mes", type=int)
    ano_ref = request.args.get("ano", type=int)

    data_inicio = datetime.strptime(inicio_str, "%Y-%m-%d").date() if inicio_str else None
    data_fim = datetime.strptime(fim_str, "%Y-%m-%d").date() if fim_str else None

    if not current_user.is_admin():
        ministro_id = current_user.id

    ministro = get_ministro_or_404(ministro_id, current_user.id_paroquia)
    missas = obter_missas_ministro_periodo(
        ministro_id=ministro.id,
        id_paroquia=current_user.id_paroquia,
        data_inicio=data_inicio,
        data_fim=data_fim
    )

    disponibilidades_data = Disponibilidade.query.filter_by(
        id_ministro=ministro.id,
        id_paroquia=current_user.id_paroquia,
    ).order_by(Disponibilidade.data.asc(), Disponibilidade.horario.asc()).all()
    disponibilidades_fixas = DisponibilidadeFixa.query.filter_by(
        id_ministro=ministro.id,
        id_paroquia=current_user.id_paroquia,
    ).order_by(DisponibilidadeFixa.dia_semana.asc(), DisponibilidadeFixa.semana.asc(), DisponibilidadeFixa.horario.asc()).all()
    indisponibilidades_data = Indisponibilidade.query.filter_by(
        id_ministro=ministro.id,
        id_paroquia=current_user.id_paroquia,
    ).order_by(Indisponibilidade.data.asc(), Indisponibilidade.horario.asc()).all()
    indisponibilidades_fixas = IndisponibilidadeFixa.query.filter_by(
        id_ministro=ministro.id,
        id_paroquia=current_user.id_paroquia,
    ).order_by(IndisponibilidadeFixa.dia_semana.asc(), IndisponibilidadeFixa.semana.asc(), IndisponibilidadeFixa.horario.asc()).all()

    reunioes = db.session.query(
        ReuniaoFormacao.data,
        ReuniaoFormacao.tipo,
        ReuniaoFormacao.assunto,
        PresencaReuniao.presente,
    ).join(
        PresencaReuniao,
        PresencaReuniao.id_reuniao == ReuniaoFormacao.id,
    ).filter(
        PresencaReuniao.id_ministro == ministro.id,
        PresencaReuniao.id_paroquia == current_user.id_paroquia,
        ReuniaoFormacao.id_paroquia == current_user.id_paroquia,
    ).order_by(
        ReuniaoFormacao.data.desc(),
        ReuniaoFormacao.id.desc(),
    ).all()

    pedidos_substituicao = db.session.query(
        PedidoSubstituicao,
        Missa,
        Ministro.nome.label("aceite_nome"),
    ).join(
        Escala,
        Escala.id == PedidoSubstituicao.id_escala,
    ).join(
        Missa,
        Missa.id == Escala.id_missa,
    ).outerjoin(
        Ministro,
        Ministro.id == PedidoSubstituicao.id_ministro_aceite,
    ).filter(
        PedidoSubstituicao.id_paroquia == current_user.id_paroquia,
        PedidoSubstituicao.id_ministro_solicitante == ministro.id,
    ).order_by(
        PedidoSubstituicao.criado_em.desc(),
    ).all()

    hoje = date.today()
    mes_base = mes_ref or (data_inicio.month if data_inicio else hoje.month)
    ano_base = ano_ref or (data_inicio.year if data_inicio else hoje.year)
    cal = calendar.monthcalendar(ano_base, mes_base)
    inicio_mes = date(ano_base, mes_base, 1)
    ultimo_dia = calendar.monthrange(ano_base, mes_base)[1]
    fim_mes = date(ano_base, mes_base, ultimo_dia)
    missas_calendario = obter_missas_ministro_periodo(
        ministro_id=ministro.id,
        id_paroquia=current_user.id_paroquia,
        data_inicio=inicio_mes,
        data_fim=fim_mes,
    )
    calendario = defaultdict(list)
    for item in missas_calendario:
        calendario[item.data.day].append(item)

    resumo_ministro = {
        "missas": len(missas),
        "confirmadas": sum(1 for item in missas if item.confirmado),
        "pendentes": sum(1 for item in missas if not item.confirmado),
        "reunioes": sum(1 for item in reunioes if item.presente),
        "pedidos_substituicao": len(pedidos_substituicao),
    }

    return render_template(
        "dashboard_ministro_detalhe.html",
        ministro=ministro,
        missas=missas,
        resumo_ministro=resumo_ministro,
        disponibilidades_data=disponibilidades_data,
        disponibilidades_fixas=disponibilidades_fixas,
        indisponibilidades_data=indisponibilidades_data,
        indisponibilidades_fixas=indisponibilidades_fixas,
        reunioes=reunioes,
        pedidos_substituicao=pedidos_substituicao,
        cal=cal,
        calendario=calendario,
        mes_ref=mes_base,
        ano_ref=ano_base,
        hoje=hoje,
        inicio=inicio_str,
        fim=fim_str,
    )


@escala_bp.route("/dashboard_ministros/substituicao/<int:escala_id>", methods=["POST"])
@login_required
def dashboard_pedir_substituicao(escala_id):
    escala = get_escala_or_404(escala_id, current_user.id_paroquia)

    if not current_user.is_admin() and escala.id_ministro != current_user.id:
        flash("Voce nao pode solicitar substituicao para esta escala.")
        return redirect(url_for("escala.dashboard_ministros"))

    pedido, enviados, links_whatsapp = criar_pedido_substituicao(escala)
    if links_whatsapp:
        flash(
            f"Pedido de substituicao aberto. Push enviados: {enviados}. "
            "Voce tambem pode avisar pelo WhatsApp."
        )
        return render_template(
            "whatsapp_lista.html",
            links=links_whatsapp,
            titulo="Avisar Disponiveis por WhatsApp",
            mensagem_topo=(
                "Os links abaixo enviam o pedido de substituicao para ministros disponiveis. "
                "Quem confirmar primeiro entra automaticamente na escala."
            ),
            voltar_url=url_for(
                "escala.dashboard_ministro_detalhe",
                ministro_id=escala.id_ministro,
            ),
        )

    flash(f"Pedido de substituicao aberto. Ministros notificados: {enviados}.")
    return redirect(
        url_for(
            "escala.dashboard_ministro_detalhe",
            ministro_id=escala.id_ministro,
        )
    )

@escala_bp.route("/escala/confirmar/<token>")
def confirmar_presenca(token):

    escala = Escala.query.filter_by(token=token).first_or_404()

    escala.confirmado = True

    db.session.commit()

    return "Presença confirmada com sucesso"













