import random
from flask import Blueprint, render_template, redirect, request, url_for, flash, send_file
from flask_login import login_required, current_user
from models import db, Ministro, Missa, Escala, Indisponibilidade, EscalaFixa
from datetime import date, timedelta
import calendar, uuid, urllib.parse, base64, io
from utils.auth import admin_required
from services.notificacao_service import (
    notificar_escala_criada,
    notificar_escala_removida
)
from services.participacao_service import obter_estatisticas_participacao

from services.substituicao_service import substituir_ministro
from services.paroquia_scope_service import (
    get_escala_fixa_or_404,
    get_escala_or_404,
    get_ministro_or_404,
    get_missa_or_404,
)

escala_bp = Blueprint("escala", __name__)

@escala_bp.route("/escala/<int:missa_id>", methods=["GET", "POST"])
@login_required
def gerar_escala(missa_id):

    missa = get_missa_or_404(missa_id, current_user.id_paroquia)
    ministros = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).all()

    if request.method == "POST":
        selecionados = request.form.getlist("ministros")
        Escala.query.filter_by(id_missa=missa.id).delete()

        for ministro_id in selecionados:
            ministro = Ministro.query.filter_by(
                id=ministro_id,
                id_paroquia=current_user.id_paroquia
            ).first()
            if not ministro:
                continue
            nova = Escala(
                id_missa=missa.id,
                id_ministro=int(ministro_id),
                id_paroquia=current_user.id_paroquia,
                token=str(uuid.uuid4())
            )
            db.session.add(nova)
            # 🔔 envia notificação
            notificar_escala_criada(ministro, missa)

        db.session.commit()

        return redirect(url_for("escala.visualizar_escala", missa_id=missa.id))

    return render_template("gerar_escala.html", missa=missa, ministros=ministros)

# ======================
# ESCALA AUTOMÁTICA
# ======================

from utils.auth import admin_required
@escala_bp.route("/escala/auto/<int:missa_id>")
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

        # indisponibilidade
        indisponivel = Indisponibilidade.query.filter(
            Indisponibilidade.id_ministro == ministro.id,
            Indisponibilidade.data == missa.data,
            Indisponibilidade.id_paroquia == current_user.id_paroquia,
            (Indisponibilidade.horario == None)
            | (Indisponibilidade.horario == missa.horario)
        ).first()

        if indisponivel:
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
                    Missa.horario == missa.horario,
                    Escala.id_paroquia == current_user.id_paroquia
                ).first()

            if conflito:
                continue

            # indisponibilidade
            indisponivel = Indisponibilidade.query.filter(
                Indisponibilidade.id_ministro == ministro.id,
                Indisponibilidade.data == missa.data,
                Indisponibilidade.id_paroquia == current_user.id_paroquia,
                (Indisponibilidade.horario == None)
                | (Indisponibilidade.horario == missa.horario)
            ).first()

            if indisponivel:
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

        # envia notificação
        notificar_escala_criada(ministro, missa)

    db.session.commit()

    flash("Escala automática gerada com sucesso!")

    return redirect(url_for("escala.visualizar_escala", missa_id=missa.id))


@escala_bp.route("/escala/visualizar/<int:missa_id>")
@login_required
def visualizar_escala(missa_id):

    missa = get_missa_or_404(missa_id, current_user.id_paroquia)

    escalas = Escala.query.filter_by(
        id_missa=missa.id,
        id_paroquia=current_user.id_paroquia
    ).all()

    ministros = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Ministro.nome).all()

    return render_template(
        "visualizar_escala.html",
        missa=missa,
        escalas=escalas,
        ministros=ministros
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

    if request.method == "POST":

        mes = int(request.form["mes"])
        ano = int(request.form["ano"])

        cal = calendar.monthcalendar(ano, mes)

        for semana in cal:
            for dia_semana, dia in enumerate(semana):

                if dia == 0:
                    continue

                data_missa = date(ano, mes, dia)
                semana_mes = (dia - 1) // 7 + 1

                # Buscar regras que se aplicam a esse dia
                regras = EscalaFixa.query.filter_by(
                    id_paroquia=current_user.id_paroquia
                ).all()

                # Filtrar regras válidas para esse dia específico
                regras_validas = []

                for regra in regras:

                    if regra.semana and regra.semana != semana_mes:
                        continue

                    if regra.dia_semana is not None and regra.dia_semana != dia_semana:
                        continue

                    regras_validas.append(regra)

                # Agrupar por horário + comunidade
                agrupado = {}

                for regra in regras_validas:
                    chave = (regra.horario, regra.comunidade)

                    if chave not in agrupado:
                        agrupado[chave] = []

                    agrupado[chave].append(regra)

                # Criar Missa e Escalas
                for (horario, comunidade), lista_regras in agrupado.items():

                    qtd_ministros = len(lista_regras)

                    missa = Missa.query.filter_by(
                        data=data_missa,
                        horario=horario,
                        id_paroquia=current_user.id_paroquia
                    ).first()

                    if not missa:
                        missa = Missa(
                            data=data_missa,
                            horario=horario,
                            comunidade=comunidade or "Matriz",
                            qtd_ministros=qtd_ministros,
                            id_paroquia=current_user.id_paroquia
                        )
                        db.session.add(missa)
                        db.session.commit()
                    else:
                        # Atualiza quantidade se já existir
                        missa.qtd_ministros = qtd_ministros
                        db.session.commit()

                    # Criar escalas
                    for regra in lista_regras:

                        escala_existente = Escala.query.filter_by(
                            id_missa=missa.id,
                            id_ministro=regra.id_ministro
                        ).first()

                        if not escala_existente:
                            nova = Escala(
                                id_missa=missa.id,
                                id_ministro=regra.id_ministro,
                                id_paroquia=current_user.id_paroquia,
                                token=str(uuid.uuid4())
                            )
                            db.session.add(nova)
                            ministro = Ministro.query.get(regra.id_ministro)
                            notificar_escala_criada(ministro, missa) 
        db.session.commit()

        flash("Escala mensal gerada automaticamente com base na escala fixa!")
        return redirect(url_for("missas.missas"))

    return render_template("form_gerar_mensal.html")


@escala_bp.route("/gerar_mensal_inteligente", methods=["GET", "POST"])
@login_required
@admin_required
def gerar_mensal_inteligente():

    from services.escala_inteligente_service import selecionar_ministros

    if request.method == "POST":

        mes = int(request.form["mes"])
        ano = int(request.form["ano"])

        cal = calendar.monthcalendar(ano, mes)

        for semana in cal:
            for dia_semana, dia in enumerate(semana):

                if dia == 0:
                    continue

                data_missa = date(ano, mes, dia)

                missas = Missa.query.filter_by(
                    data=data_missa,
                    id_paroquia=current_user.id_paroquia
                ).all()

                for missa in missas:

                    # limpa escala antiga
                    Escala.query.filter_by(id_missa=missa.id).delete()

                    ministros = selecionar_ministros(
                        missa.qtd_ministros,
                        current_user.id_paroquia,
                        missa
                    )

                    for ministro in ministros:

                        nova = Escala(
                            id_missa=missa.id,
                            id_ministro=ministro.id,
                            id_paroquia=current_user.id_paroquia,
                            token=str(uuid.uuid4())
                        )

                        db.session.add(nova)

                        notificar_escala_criada(ministro, missa)

        db.session.commit()

        flash("Escala mensal inteligente gerada com sucesso!")

        return redirect(url_for("missas.missas"))

    return render_template("form_gerar_mensal_inteligente.html")

from sqlalchemy import extract

@escala_bp.route("/gerar_mensal_super_inteligente", methods=["GET", "POST"])
@login_required
@admin_required
def gerar_mensal_super_inteligente():

    from services.escala_inteligente_service import selecionar_ministros

    if request.method == "POST":

        mes = int(request.form["mes"])
        ano = int(request.form["ano"])

        # ===============================
        # 1️⃣ LIMPAR ESCALAS DO MÊS
        # ===============================

        Escala.query.join(Missa).filter(
            Escala.id_paroquia == current_user.id_paroquia,
            extract("month", Missa.data) == mes,
            extract("year", Missa.data) == ano
        ).delete(synchronize_session=False)

        db.session.commit()

        # ===============================
        # 2️⃣ DEFINIR INTERVALO DO MÊS
        # ===============================

        inicio = date(ano, mes, 1)
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        fim = date(ano, mes, ultimo_dia)

        dia_atual = inicio

        # ===============================
        # 3️⃣ PERCORRER DIAS DO MÊS
        # ===============================

        while dia_atual <= fim:

            missas = Missa.query.filter_by(
                data=dia_atual,
                id_paroquia=current_user.id_paroquia
            ).all()

            for missa in missas:

                # ===============================
                # GERAR MINISTROS INTELIGENTES
                # ===============================

                ministros = selecionar_ministros(
                    missa.qtd_ministros,
                    current_user.id_paroquia,
                    missa
                )

                for ministro in ministros:

                    nova = Escala(
                        id_missa=missa.id,
                        id_ministro=ministro.id,
                        id_paroquia=current_user.id_paroquia,
                        token=str(uuid.uuid4())
                    )

                    db.session.add(nova)

                    # 🔔 enviar notificação
                    notificar_escala_criada(ministro, missa)

            dia_atual += timedelta(days=1)

        # ===============================
        # 4️⃣ SALVAR NO BANCO
        # ===============================

        db.session.commit()

        flash("⚡ Escala inteligente do mês gerada com sucesso!")

        return redirect(url_for("missas.missas"))

    return render_template("form_gerar_mensal_super.html")

from utils.auth import admin_required
@escala_bp.route("/escala/remover/<int:escala_id>", methods=["POST"])
@login_required
@admin_required
def remover_ministro_escala(escala_id):

    escala = get_escala_or_404(escala_id, current_user.id_paroquia)

    ministro = escala.ministro
    missa = escala.missa
    missa_id = escala.id_missa

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
    missa = get_missa_or_404(missa_id, current_user.id_paroquia)
    ministro = get_ministro_or_404(ministro_id, current_user.id_paroquia)

    existe = Escala.query.filter_by(
        id_missa=missa_id,
        id_ministro=ministro_id
    ).first()

    if not existe:
        nova = Escala(
            id_missa=missa_id,
            id_ministro=ministro_id,
            id_paroquia=current_user.id_paroquia,
            token=str(uuid.uuid4())
        )
        db.session.add(nova)
        
        notificar_escala_criada(ministro, missa)

        db.session.commit()

    return redirect(url_for("escala.visualizar_escala", missa_id=missa_id))


@escala_bp.route("/salvar_mensal", methods=["POST"])
@login_required
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

                if not escala_existente:
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

            # remove da escala
            db.session.delete(escala)
            db.session.commit()

            # chama substituto automático
            substituir_ministro(escala)

            flash("Você foi removido da escala. Um substituto será chamado.")

            return redirect(url_for("publico.calendario_paroquia", id=paroquia_id))

    return render_template(
        "escala_publica.html",
        escala=escala,
        missa=escala.missa,
        ministro=escala.ministro
    )

@escala_bp.route("/dashboard_ministros")
@login_required
@admin_required
def dashboard_ministros():
    resultado = obter_estatisticas_participacao(current_user.id_paroquia)

    return render_template(
        "dashboard_ministros.html",
        dados=resultado["dados"],
        resumo=resultado["resumo"]
    )



