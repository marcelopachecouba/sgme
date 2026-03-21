
from datetime import datetime
import io
import urllib.parse
from collections import defaultdict
import os
from flask import Blueprint, render_template, request, url_for, send_file
from flask_login import login_required, current_user
from models import db, Ministro, Missa, Escala
from utils.auth import admin_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from services.estatisticas_service import dados_confiabilidade
from services.public_url_service import build_public_url
from services.relatorio_service import montar_mensagem_unificada

estatisticas_bp = Blueprint("estatisticas", __name__)

import routes.auth_routes as auth

from services.relatorio_service import obter_saudacao

@estatisticas_bp.route("/estatisticas", methods=["GET", "POST"])
@login_required
@admin_required
def estatisticas():
    saudacao = obter_saudacao()
    data_inicio = ""
    data_fim = ""

    query = Escala.query.join(Missa).join(Ministro).filter(
        Escala.id_paroquia == current_user.id_paroquia
    )

    if request.method == "POST":

        data_inicio = request.form.get("data_inicio")
        data_fim = request.form.get("data_fim")

        if data_inicio:
            data_inicio_date = datetime.strptime(data_inicio, "%Y-%m-%d").date()
            query = query.filter(db.func.date(Missa.data) >= data_inicio_date)

        if data_fim:
            data_fim_date = datetime.strptime(data_fim, "%Y-%m-%d").date()
            query = query.filter(db.func.date(Missa.data) <= data_fim_date)

    escalas = query.order_by(Ministro.nome, Missa.data).all()

    # 🔥 AGRUPAMENTO POR MINISTRO
    dados = {}

    for e in escalas:
        nome = e.ministro.nome

        if nome not in dados:
            dados[nome] = {
                "total": 0,
                "missas": []
            }

        dados[nome]["total"] += 1
        dados[nome]["missas"].append(e)

    return render_template(
        "estatisticas.html",
        dados=dados,
        data_inicio=data_inicio,
        data_fim=data_fim
    )


@estatisticas_bp.route("/estatisticas/pdf", methods=["POST"])
@login_required
def estatisticas_pdf():

    data_inicio = request.form.get("data_inicio")
    data_fim = request.form.get("data_fim")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()
    elements.append(Paragraph("Relatório de Escalas", styles["Heading1"]))
    elements.append(Spacer(1, 12))

    query = Escala.query.join(Missa).join(Ministro).filter(
        Escala.id_paroquia == current_user.id_paroquia
    )

    if data_inicio:
        query = query.filter(db.func.date(Missa.data) >= data_inicio)

    if data_fim:
        query = query.filter(db.func.date(Missa.data) <= data_fim)

    escalas = query.all()

    data_table = [["Ministro", "Data", "Horário", "Comunidade"]]

    for e in escalas:
        data_table.append([
            e.ministro.nome,
            e.missa.data.strftime("%d/%m/%Y"),
            e.missa.horario,
            e.missa.comunidade
        ])

    table = Table(data_table)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.grey),
        ("GRID", (0,0), (-1,-1), 1, colors.black)
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    return send_file(buffer, as_attachment=True,
                     download_name="relatorio_escalas.pdf",
                     mimetype="application/pdf")
@estatisticas_bp.route("/estatisticas/whatsapp", methods=["POST"])
@login_required
@admin_required
def whatsapp_periodo():

    data_inicio = request.form.get("data_inicio")
    data_fim = request.form.get("data_fim")

    query = Escala.query.join(Missa).join(Ministro).filter(
        Escala.id_paroquia == current_user.id_paroquia,
        Escala.confirmado == False
    )

    if data_inicio:
        data_inicio_date = datetime.strptime(data_inicio, "%Y-%m-%d").date()
        query = query.filter(db.func.date(Missa.data) >= data_inicio_date)

    if data_fim:
        data_fim_date = datetime.strptime(data_fim, "%Y-%m-%d").date()
        query = query.filter(db.func.date(Missa.data) <= data_fim_date)

    escalas = query.order_by(Ministro.nome, Missa.data).all()

    ministros_dict = defaultdict(list)

    for e in escalas:
        if e.ministro and e.ministro.telefone:
            ministros_dict[e.ministro].append(e)

    links = []

    for ministro, lista_escalas in ministros_dict.items():
        import routes.auth_routes as auth
        saudacao = obter_saudacao()

        mensagem = f"{saudacao} {ministro.nome},\n\n"
        mensagem += "Esse é um lembrete para sua próxima escala do grupo Ministério da Eucaristia.\n\n"

        # 🔹 FORMATA DATA EM PORTUGUÊS
        meses = {
            1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
            7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"
        }

        for escala in lista_escalas:
            missa = escala.missa

            dia = missa.data.day
            mes = meses[missa.data.month]
            ano = missa.data.year

            mensagem += f"Data: {dia} de {mes} de {ano}\n"
            mensagem += f"Horário: {missa.horario}\n"
            mensagem += f"Comunidade: {missa.comunidade}\n\n"

        # 🔹 LINK ESCALA ESPECÍFICA
        link_especifico = build_public_url(
            "escala.escala_publica",
            token=lista_escalas[0].token,
        )

        mensagem += "🔗 Acessar escala:\n"
        mensagem += f"{link_especifico}\n\n"

        # 🔹 LINK CALENDÁRIO COMPLETO
        if ministro.token_publico:
            link_calendario = build_public_url(
                "publico.calendario_publico",
                token=ministro.token_publico,
            )

            mensagem += "📅 Ver meu calendário completo:\n"
            mensagem += f"{link_calendario}\n"

        mensagem_codificada = urllib.parse.quote(mensagem)

        link = f"https://wa.me/55{ministro.telefone}?text={mensagem_codificada}"

        links.append({
            "nome": ministro.nome,
            "link": link
        })

    return render_template("whatsapp_lista.html", links=links)

from utils.auth import admin_required
@estatisticas_bp.route("/confiabilidade")
@login_required
#@admin_required
def confiabilidade():
    dados = dados_confiabilidade(current_user.id_paroquia)
    return render_template("confiabilidade.html", dados=dados)

@estatisticas_bp.route("/estatisticas/whatsapp_relatorio", methods=["POST"])
@login_required
@admin_required
def whatsapp_relatorio():

    data_inicio = request.form.get("data_inicio")
    data_fim = request.form.get("data_fim")

    query = Escala.query.join(Missa).join(Ministro).filter(
        Escala.id_paroquia == current_user.id_paroquia
    )

    if data_inicio:
        data_inicio_date = datetime.strptime(data_inicio, "%Y-%m-%d").date()
        query = query.filter(db.func.date(Missa.data) >= data_inicio_date)

    if data_fim:
        data_fim_date = datetime.strptime(data_fim, "%Y-%m-%d").date()
        query = query.filter(db.func.date(Missa.data) <= data_fim_date)

    escalas = query.order_by(Ministro.nome, Missa.data).all()

    from collections import defaultdict
    ministros_dict = defaultdict(list)

    for e in escalas:
        if e.ministro and e.ministro.telefone:
            ministros_dict[e.ministro].append(e)

    links = []

    for ministro, lista_escalas in ministros_dict.items():

        mensagem = montar_mensagem_unificada(ministro, lista_escalas)
        mensagem_codificada = urllib.parse.quote(mensagem)

        link = f"https://wa.me/55{ministro.telefone}?text={mensagem_codificada}"

        links.append({
            "nome": ministro.nome,
            "qtd": len(lista_escalas),
            "link": link
        })

    return render_template("whatsapp_lista.html", links=links)

@estatisticas_bp.route("/estatisticas/whatsapp_auto", methods=["POST"])
@login_required
@admin_required
def whatsapp_auto():

    data_inicio = request.form.get("data_inicio")
    data_fim = request.form.get("data_fim")

    query = Escala.query.join(Missa).join(Ministro).filter(
        Escala.id_paroquia == current_user.id_paroquia
    )

    if data_inicio:
        data_inicio_date = datetime.strptime(data_inicio, "%Y-%m-%d").date()
        query = query.filter(db.func.date(Missa.data) >= data_inicio_date)

    if data_fim:
        data_fim_date = datetime.strptime(data_fim, "%Y-%m-%d").date()
        query = query.filter(db.func.date(Missa.data) <= data_fim_date)

    escalas = query.order_by(Ministro.nome, Missa.data).all()

    from collections import defaultdict
    ministros_dict = defaultdict(list)

    for e in escalas:
        if e.ministro and e.ministro.telefone:
            ministros_dict[e.ministro].append(e)

    # inicia WhatsApp
    iniciar_driver()

    for ministro, lista_escalas in ministros_dict.items():

        saudacao = obter_saudacao()

        mensagem = f"{saudacao} {ministro.nome} 🙏\n\n"
        mensagem += "Segue sua escala do período:\n\n"

        for escala in lista_escalas:
            missa = escala.missa
            semana = ((missa.data.day - 1) // 7) + 1

            dias = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]

            mensagem += (
                f"{missa.data.strftime('%d/%m')} - "
                f"{dias[missa.data.weekday()]} ({semana}ª semana)\n"
                f"{missa.horario} - {missa.comunidade}\n\n"
            )

        mensagem += "Deus abençoe seu serviço 🙏"

        enviar_mensagem(ministro.telefone, mensagem)

    return "Mensagens enviadas com sucesso!"

@estatisticas_bp.route("/estatisticas/exportar_whatsapp", methods=["POST"])
@login_required
@admin_required
def exportar_whatsapp():

    import json
    from collections import defaultdict

    data_inicio = request.form.get("data_inicio")
    data_fim = request.form.get("data_fim")

    query = Escala.query.join(Missa).join(Ministro).filter(
        Escala.id_paroquia == current_user.id_paroquia
    )

    if data_inicio:
        data_inicio_date = datetime.strptime(data_inicio, "%Y-%m-%d").date()
        query = query.filter(db.func.date(Missa.data) >= data_inicio_date)

    if data_fim:
        data_fim_date = datetime.strptime(data_fim, "%Y-%m-%d").date()
        query = query.filter(db.func.date(Missa.data) <= data_fim_date)

    escalas = query.order_by(Ministro.nome, Missa.data).all()

    ministros_dict = defaultdict(list)

    for e in escalas:
        if e.ministro and e.ministro.telefone:
            ministros_dict[e.ministro].append(e)

    dados = []

    for ministro, lista in ministros_dict.items():

        missas = []

        for e in lista:
            missas.append({
                "data": e.missa.data.strftime("%d/%m/%Y"),
                "dia_semana": e.missa.data.weekday(),
                "horario": e.missa.horario,
                "comunidade": e.missa.comunidade
            })

        dados.append({
            "nome": ministro.nome,
            "telefone": ministro.telefone,
            "missas": missas
        })

    return json.dumps(dados, ensure_ascii=False)
