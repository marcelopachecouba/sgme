
from ofertas.sicredi_service import buscar_pix_sicredi
from datetime import datetime, timedelta, timezone

from models import OfertaRecebida

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file
)

from extensions import db

from models import (
    Comunidade,
    TipoArrecadacao,
    OfertaRecebida
)

ofertas_bp = Blueprint(
    "ofertas",
    __name__,
    url_prefix="/ofertas"
)


@ofertas_bp.route("/comunidades")
def comunidades():

    lista = Comunidade.query.order_by(
        Comunidade.nome
    ).all()

    return render_template(
        "ofertas/comunidades.html",
        lista=lista
    )

from models import Comunidade, TipoArrecadacao

@ofertas_bp.route(
    "/comunidades/novo",
    methods=["GET","POST"]
)
def comunidade_nova():

    tipos = TipoArrecadacao.query.filter_by(
        ativo=True
    ).order_by(
        TipoArrecadacao.descricao
    ).all()

    if request.method == "POST":

        c = Comunidade()

        c.nome = request.form["nome"]
        c.codigo = request.form["codigo"]
        c.txid = request.form["txid"]
        c.tipo_id = request.form["tipo_id"]
        c.chave_pix = request.form["chave_pix"]
        c.responsavel = request.form["responsavel"]
        c.telefone = request.form["telefone"]
        c.cor = request.form["cor"]
        c.ativa = request.form.get("ativa") == "1"

        db.session.add(c)
        db.session.commit()

        return redirect(url_for("ofertas.comunidades"))

    return render_template(
        "ofertas/comunidade_form.html",
        tipos=tipos
    )



@ofertas_bp.route(
    "/comunidades/<int:id>",
    methods=["GET", "POST"]
)
def editar_comunidade(id):

    c = Comunidade.query.get_or_404(id)

    tipos = TipoArrecadacao.query.filter_by(
        ativo=True
    ).order_by(
        TipoArrecadacao.descricao
    ).all()

    if request.method == "POST":

        c.nome = request.form["nome"]

        c.codigo = request.form["codigo"].upper()

        c.txid = request.form["txid"].upper()

        c.tipo_id = request.form["tipo_id"]

        c.chave_pix = request.form["chave_pix"]

        c.responsavel = request.form["responsavel"]

        c.telefone = request.form["telefone"]

        c.cor = request.form["cor"]

        c.ativa = request.form.get("ativa") == "1"

        db.session.commit()

        flash("Registro alterado.")

        return redirect(
            url_for("ofertas.comunidades")
        )

    return render_template(
        "ofertas/comunidade_form.html",
        comunidade=c,
        tipos=tipos
    )

@ofertas_bp.route(
    "/comunidades/excluir/<int:id>"
)
def excluir_comunidade(id):

    c = Comunidade.query.get_or_404(id)

    db.session.delete(c)

    db.session.commit()

    flash("Comunidade excluída.")

    return redirect(
        url_for("ofertas.comunidades")
    )


import qrcode


#----------------------------------------
# CRC16
#----------------------------------------

def crc16(payload):

    crc = 0xFFFF

    for c in payload:

        crc ^= ord(c) << 8

        for _ in range(8):

            if crc & 0x8000:

                crc = (
                    (crc << 1)
                    ^
                    0x1021
                ) & 0xFFFF

            else:

                crc = (
                    crc << 1
                ) & 0xFFFF

    return format(crc, "04X")


#----------------------------------------
# TAG
#----------------------------------------

def tag(id, valor):

    return (
        id +
        str(len(valor)).zfill(2) +
        valor
    )


#----------------------------------------
# GERA PIX
#----------------------------------------

def gerar_pix(
        chave,
        nome,
        cidade,
        identificacao):

    merchant = ""

    merchant += tag(
        "00",
        "BR.GOV.BCB.PIX"
    )

    merchant += tag(
        "01",
        chave
    )

    payload = ""

    payload += tag(
        "00",
        "01"
    )

    payload += tag(
        "01",
        "11"
    )

    payload += tag(
        "26",
        merchant
    )

    payload += tag(
        "52",
        "0000"
    )

    payload += tag(
        "53",
        "986"
    )

    payload += tag(
        "58",
        "BR"
    )

    payload += tag(
        "59",
        nome[:25]
    )

    payload += tag(
        "60",
        cidade[:15]
    )

    adicional = tag(
        "05",
        identificacao
    )

    payload += tag(
        "62",
        adicional
    )

    payload += "6304"

    payload += crc16(payload)

    return payload

# -----------------------
# QRCode
# -----------------------

@ofertas_bp.route("/qrcode/<int:id>")
def gerar_qrcode(id):

    import os

    comunidade = Comunidade.query.get_or_404(id)

    payload = gerar_pix(

        chave=comunidade.chave_pix,

        nome="PAROQUIA NS APARECIDA",

        cidade="PALMAS",

        identificacao=comunidade.txid

    )

    qr = qrcode.QRCode(

        version=None,

        error_correction=qrcode.constants.ERROR_CORRECT_M,

        box_size=10,

        border=4

    )

    qr.add_data(payload)

    qr.make(fit=True)

    img = qr.make_image(

        fill_color="black",

        back_color="white"

    )

    os.makedirs(

        "static/qrcodes",

        exist_ok=True

    )

    caminho = os.path.join(

        "static",

        "qrcodes",

        f"{comunidade.txid}.png"

    )

    img.save(caminho)

    return send_file(

        caminho,

        mimetype="image/png",

        as_attachment=False

    )


@ofertas_bp.route("/recebidas")
def ofertas():

    lista = OfertaRecebida.query.order_by(

        OfertaRecebida.datahora.desc()

    ).all()

    return render_template(

        "ofertas/ofertas.html",

        lista=lista

    )

@ofertas_bp.route("/relatorios", methods=["GET", "POST"])
def relatorios():

    comunidades = Comunidade.query.order_by(
        Comunidade.nome
    ).all()

    tipos = TipoArrecadacao.query.order_by(
        TipoArrecadacao.descricao
    ).all()

    consulta = OfertaRecebida.query

    if request.method == "POST":

        data_inicial = request.form.get("data_inicial")
        data_final = request.form.get("data_final")
        comunidade = request.form.get("comunidade")
        tipo = request.form.get("tipo")

        if data_inicial:
            consulta = consulta.filter(
                OfertaRecebida.datahora >= data_inicial
            )

        if data_final:
            consulta = consulta.filter(
                OfertaRecebida.datahora <=
                data_final + " 23:59:59"
            )

        if comunidade:
            consulta = consulta.filter(
                OfertaRecebida.comunidade_id == comunidade
            )

        if tipo:
            consulta = consulta.filter(
                OfertaRecebida.tipo_id == tipo
            )

    lista = consulta.order_by(
        OfertaRecebida.datahora.desc()
    ).all()

    total = sum(
        float(x.valor)
        for x in lista
    )

    return render_template(

        "ofertas/relatorios.html",

        lista=lista,

        total=total,

        comunidades=comunidades,

        tipos=tipos

    )

@ofertas_bp.route("/imprimir_qrcode/<int:id>")
def imprimir_qrcode(id):

    comunidade = Comunidade.query.get_or_404(id)

    return render_template(

        "ofertas/imprimir_qrcode.html",

        comunidade=comunidade

    )

@ofertas_bp.route(
    "/importar_pix",
    methods=["GET", "POST"]
)
def importar_pix():

    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo

    TZ_BR = ZoneInfo("America/Sao_Paulo")

    if request.method == "GET":

        return render_template(
            "ofertas/ofertas_importar.html"
        )

    data_inicial = request.form["data_inicial"]
    data_final = request.form["data_final"]

    agora = datetime.now(
        timezone.utc
    ).astimezone(
        TZ_BR
    )

    comunidades = {
        c.txid.strip().upper(): c
        for c in Comunidade.query.all()
        if c.txid
    }

    total = 0

    dia = datetime.strptime(
        data_inicial,
        "%Y-%m-%d"
    )

    ultimo = datetime.strptime(
        data_final,
        "%Y-%m-%d"
    )

    while dia <= ultimo:

        inicio = dia.strftime(
            "%Y-%m-%dT00:00:00-03:00"
        )

        # Se for hoje usa a hora atual
        if dia.date() == agora.date():

            fim = agora.strftime(
                "%Y-%m-%dT%H:%M:%S-03:00"
            )

        else:

            fim = dia.strftime(
                "%Y-%m-%dT23:59:59-03:00"
            )

        print("=================================")
        print("IMPORTANDO PIX")
        print("INICIO:", inicio)
        print("FIM:", fim)
        print("=================================")

        lista = buscar_pix_sicredi(
            inicio=inicio,
            fim=fim
        )

        for pix in lista:

            txid = (
                pix.get("txid") or ""
            ).strip().upper()

            if not txid:
                continue

            comunidade = comunidades.get(txid)

            if comunidade is None:

                print(
                    "Comunidade não encontrada:",
                    txid
                )

                continue

            endtoendid = pix.get(
                "endToEndId",
                ""
            )

            if OfertaRecebida.query.filter_by(
                endtoendid=endtoendid
            ).first():

                continue

            oferta = OfertaRecebida()

            oferta.txid = txid

            oferta.endtoendid = endtoendid

            oferta.codigo_autenticacao = (

                pix.get("codigoAutenticacao")

                or

                pix.get("idTransacao")

                or ""

            )

            oferta.valor = float(
                pix.get(
                    "valor",
                    0
                )
            )

            horario = pix.get(
                "horario"
            )

            if horario:

                try:

                    utc = datetime.fromisoformat(

                        horario.replace(
                            "Z",
                            "+00:00"
                        )

                    )

                    oferta.datahora = utc.astimezone(
                        TZ_BR
                    ).replace(
                        tzinfo=None
                    )

                except Exception:

                    oferta.datahora = agora.replace(
                        tzinfo=None
                    )

            else:

                oferta.datahora = agora.replace(
                    tzinfo=None
                )

            oferta.chave_pix = pix.get(
                "chave",
                ""
            )

            oferta.payload = pix

            oferta.comunidade_id = comunidade.id

            oferta.tipo_id = comunidade.tipo_id

            db.session.add(
                oferta
            )

            total += 1

        dia += timedelta(days=1)

    db.session.commit()

    flash(
        f"✅ {total} PIX importados com sucesso!",
        "success"
    )

    return redirect(
        url_for("ofertas.ofertas")
    )

@ofertas_bp.route("/relatorio_comunidade", methods=["GET", "POST"])
def relatorio_comunidade():

    consulta = db.session.query(

        Comunidade.nome,

        db.func.count(OfertaRecebida.id).label("quantidade"),

        db.func.sum(OfertaRecebida.valor).label("total")

    ).join(

        OfertaRecebida,

        OfertaRecebida.comunidade_id == Comunidade.id

    )

    if request.method == "POST":

        data_inicial = request.form.get("data_inicial")
        data_final = request.form.get("data_final")

        if data_inicial:

            consulta = consulta.filter(
                OfertaRecebida.datahora >= data_inicial
            )

        if data_final:

            consulta = consulta.filter(
                OfertaRecebida.datahora <= data_final + " 23:59:59"
            )

    lista = consulta.group_by(
        Comunidade.nome
    ).order_by(
        Comunidade.nome
    ).all()

    total_geral = sum(
        float(x.total or 0)
        for x in lista
    )

    return render_template(

        "ofertas/relatorio_comunidade.html",

        lista=lista,

        total_geral=total_geral

    )


from sqlalchemy import func

@ofertas_bp.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    data_inicial = None
    data_final = None
    comunidade_id = None

    consulta = OfertaRecebida.query

    comunidades_lista = Comunidade.query.order_by(
        Comunidade.nome
    ).all()

    if request.method == "POST":

        data_inicial = request.form.get("data_inicial")
        data_final = request.form.get("data_final")
        comunidade_id = request.form.get("comunidade")

        if data_inicial:

            consulta = consulta.filter(
                OfertaRecebida.datahora >=
                datetime.strptime(
                    data_inicial,
                    "%Y-%m-%d"
                )
            )

        if data_final:

            consulta = consulta.filter(
                OfertaRecebida.datahora <=
                datetime.strptime(
                    data_final + " 23:59:59",
                    "%Y-%m-%d %H:%M:%S"
                )
            )

        if comunidade_id:

            consulta = consulta.filter(
                OfertaRecebida.comunidade_id == int(comunidade_id)
            )

    total = sum(
        float(x.valor)
        for x in consulta.all()
    )

    quantidade = consulta.count()

    ranking = db.session.query(

        Comunidade.nome,

        db.func.sum(
            OfertaRecebida.valor
        ).label("total")

    ).join(

        OfertaRecebida,

        OfertaRecebida.comunidade_id == Comunidade.id

    )

    if data_inicial:

        ranking = ranking.filter(
            OfertaRecebida.datahora >=
            datetime.strptime(
                data_inicial,
                "%Y-%m-%d"
            )
        )

    if data_final:

        ranking = ranking.filter(
            OfertaRecebida.datahora <=
            datetime.strptime(
                data_final + " 23:59:59",
                "%Y-%m-%d %H:%M:%S"
            )
        )

    if comunidade_id:

        ranking = ranking.filter(
            OfertaRecebida.comunidade_id == int(comunidade_id)
        )

    ranking = ranking.group_by(
        Comunidade.nome
    ).order_by(
        db.func.sum(
            OfertaRecebida.valor
        ).desc()
    ).all()

    return render_template(

        "ofertas/dashboard.html",

        total=total,

        quantidade=quantidade,

        comunidades=ranking,

        lista_comunidades=comunidades_lista,

        data_inicial=data_inicial,

        data_final=data_final,

        comunidade_id=comunidade_id

    )



@ofertas_bp.route("/ranking", methods=["GET", "POST"])
def ranking_comunidades():

    data_inicial = None
    data_final = None

    consulta = db.session.query(

        Comunidade.id,

        Comunidade.nome,

        db.func.count(
            OfertaRecebida.id
        ).label("qtd_pix"),

        db.func.sum(
            OfertaRecebida.valor
        ).label("total")

    ).join(

        OfertaRecebida,

        OfertaRecebida.comunidade_id == Comunidade.id

    )

    if request.method == "POST":

        data_inicial = request.form.get("data_inicial")
        data_final = request.form.get("data_final")

        if data_inicial:

            consulta = consulta.filter(

                OfertaRecebida.datahora >=

                datetime.strptime(
                    data_inicial,
                    "%Y-%m-%d"
                )

            )

        if data_final:

            consulta = consulta.filter(

                OfertaRecebida.datahora <=

                datetime.strptime(
                    data_final + " 23:59:59",
                    "%Y-%m-%d %H:%M:%S"
                )

            )

    ranking = consulta.group_by(

        Comunidade.id,
        Comunidade.nome

    ).order_by(

        db.func.sum(
            OfertaRecebida.valor
        ).desc()

    ).all()

    total_geral = sum(
        float(x.total or 0)
        for x in ranking
    )

    return render_template(

        "ofertas/ranking.html",

        ranking=ranking,

        total_geral=total_geral,

        data_inicial=data_inicial,

        data_final=data_final

    )

# ============================
# EXPORTAR EXCEL
# ============================

from flask import request, send_file
from openpyxl import Workbook
from io import BytesIO


@ofertas_bp.route("/exportar_excel")
def exportar_excel():

    data_inicial = request.args.get("data_inicial")
    data_final = request.args.get("data_final")
    comunidade_id = request.args.get("comunidade")

    consulta = OfertaRecebida.query

    if data_inicial:

        consulta = consulta.filter(

            OfertaRecebida.datahora >=

            datetime.strptime(
                data_inicial,
                "%Y-%m-%d"
            )

        )

    if data_final:

        consulta = consulta.filter(

            OfertaRecebida.datahora <=

            datetime.strptime(
                data_final + " 23:59:59",
                "%Y-%m-%d %H:%M:%S"
            )

        )

    if comunidade_id:

        consulta = consulta.filter(

            OfertaRecebida.comunidade_id == int(comunidade_id)

        )

    lista = consulta.order_by(
        OfertaRecebida.datahora
    ).all()

    wb = Workbook()

    ws = wb.active

    ws.title = "Ofertas"

    ws.append([

        "Data",

        "Comunidade",

        "Tipo",

        "TXID",

        "Valor"

    ])

    total = 0

    for o in lista:

        total += float(o.valor)

        ws.append([

            o.datahora.strftime(
                "%d/%m/%Y %H:%M"
            ),

            o.comunidade.nome if o.comunidade else "",

            o.tipo.descricao if o.tipo else "",

            o.txid,

            float(o.valor)

        ])

    ws.append([])

    ws.append([
        "",
        "",
        "",
        "TOTAL",
        total
    ])

    arquivo = BytesIO()

    wb.save(arquivo)

    arquivo.seek(0)

    return send_file(

        arquivo,

        as_attachment=True,

        download_name="Prestacao_Contas.xlsx",

        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    )


# ============================
# PDF
# ============================

from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle
)

from reportlab.lib import colors


@ofertas_bp.route("/imprimir_pdf")
def imprimir_pdf():

    data_inicial = request.args.get("data_inicial")
    data_final = request.args.get("data_final")
    comunidade_id = request.args.get("comunidade")

    consulta = OfertaRecebida.query

    if data_inicial:

        consulta = consulta.filter(

            OfertaRecebida.datahora >=

            datetime.strptime(
                data_inicial,
                "%Y-%m-%d"
            )

        )

    if data_final:

        consulta = consulta.filter(

            OfertaRecebida.datahora <=

            datetime.strptime(
                data_final + " 23:59:59",
                "%Y-%m-%d %H:%M:%S"
            )

        )

    if comunidade_id:

        consulta = consulta.filter(

            OfertaRecebida.comunidade_id == int(comunidade_id)

        )

    lista = consulta.order_by(
        OfertaRecebida.datahora
    ).all()

    buffer = BytesIO()

    doc = SimpleDocTemplate(buffer)

    dados = [[

        "Data",

        "Comunidade",

        "Tipo",

        "ID",

        "Valor"

    ]]

    total = 0

    for o in lista:

        total += float(o.valor)

        dados.append([

            o.datahora.strftime(
                "%d/%m/%Y %H:%M"
            ),

            o.comunidade.nome if o.comunidade else "",

            o.tipo.descricao if o.tipo else "",

            o.endtoendid,

            f"R$ {o.valor:.2f}"

        ])

    dados.append([

        "",

        "",

        "",
        

        "TOTAL",

        f"R$ {total:.2f}"

    ])

    tabela = Table(dados)

    tabela.setStyle(TableStyle([

        ("GRID",(0,0),(-1,-1),1,colors.black),

        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),

        ("BACKGROUND",(0,-1),(-1,-1),colors.lightgreen),

        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),

        ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),

        ("ALIGN",(4,1),(4,-1),"RIGHT"),

        ("FONTSIZE",(0,0),(-1,-1),9)

    ]))

    doc.build([tabela])

    buffer.seek(0)

    return send_file(

        buffer,

        as_attachment=False,

        download_name="Prestacao_Contas.pdf",

        mimetype="application/pdf"

    )

#Rotina IMportação Pix


@ofertas_bp.route("/importar_pix_automatico")
def importar_pix_automatico():

    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo

    TZ_BR = ZoneInfo("America/Sao_Paulo")

    # Hora atual correta no Brasil
    agora = (
        datetime.now(timezone.utc)
        .astimezone(TZ_BR)
    )

    # Consulta sempre as últimas 6 horas
    inicio_dt = (
        agora - timedelta(hours=6)
    )

    inicio_api = inicio_dt.strftime(
        "%Y-%m-%dT%H:%M:%S-03:00"
    )

    fim_api = agora.strftime(
        "%Y-%m-%dT%H:%M:%S-03:00"
    )

    print("===================================")
    print("IMPORTAÇÃO AUTOMÁTICA PIX")
    print("INÍCIO:", inicio_api)
    print("FIM   :", fim_api)
    print("===================================")

    try:

        lista = buscar_pix_sicredi(

            inicio=inicio_api,

            fim=fim_api

        )

    except Exception as e:

        print("ERRO API PIX:", str(e))

        return str(e)

    comunidades = {

        c.txid.strip().upper(): c

        for c in Comunidade.query.all()

        if c.txid

    }

    total = 0
    duplicados = 0
    ignorados = 0

    for pix in lista:

        txid = (
            pix.get("txid") or ""
        ).strip().upper()

        if not txid:

            ignorados += 1
            continue

        comunidade = comunidades.get(txid)

        if comunidade is None:

            print(
                "Comunidade não encontrada:",
                txid
            )

            ignorados += 1
            continue

        endtoendid = pix.get(
            "endToEndId",
            ""
        )

        if OfertaRecebida.query.filter_by(

            endtoendid=endtoendid

        ).first():

            duplicados += 1
            continue

        oferta = OfertaRecebida()

        oferta.txid = txid

        oferta.endtoendid = endtoendid

        oferta.codigo_autenticacao = (

            pix.get("codigoAutenticacao")

            or

            pix.get("idTransacao")

            or ""

        )

        oferta.valor = float(

            pix.get(
                "valor",
                0
            )

        )

        horario = pix.get("horario")

        if horario:

            try:

                utc = datetime.fromisoformat(

                    horario.replace(
                        "Z",
                        "+00:00"
                    )

                )

                oferta.datahora = utc.astimezone(

                    TZ_BR

                ).replace(

                    tzinfo=None

                )

            except Exception:

                oferta.datahora = agora.replace(
                    tzinfo=None
                )

        else:

            oferta.datahora = agora.replace(
                tzinfo=None
            )

        oferta.chave_pix = pix.get(
            "chave",
            ""
        )

        oferta.payload = pix

        oferta.comunidade_id = comunidade.id

        oferta.tipo_id = comunidade.tipo_id

        db.session.add(oferta)

        total += 1

        print(
            f"IMPORTADO: {txid} - "
            f"{oferta.valor:.2f}"
        )

    db.session.commit()

    print("===================================")
    print("PIX API.....:", len(lista))
    print("IMPORTADOS..:", total)
    print("DUPLICADOS..:", duplicados)
    print("IGNORADOS...:", ignorados)
    print("===================================")

    return f"{total} PIX importados automaticamente."


@ofertas_bp.route("/", methods=["GET"])
def inicio():

    return render_template(
        "ofertas/index.html"
    )

