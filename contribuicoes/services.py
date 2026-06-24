from flask import session
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from types import SimpleNamespace

from flask import current_app
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import extract, func

from extensions import db
from models import Comunidade
from rifas.payments import (
    get_pix_gateway,
    _gerar_qr_code_base64,
)


from .models import CategoriaContribuicao, Contribuicao, Dizimista, ReciboContribuicao


CATEGORIAS_PADRAO = [
    ("dizimo", "Dizimo"),
    ("doacao", "Doacao"),
    ("oferta", "Oferta"),
    ("campanha", "Campanha"),
    ("construcao", "Fundo de Construcao"),
    ("evangelizacao", "Evangelizacao"),
]

STATUS_PENDENTE = "pendente"
STATUS_PAGO = "pago"
STATUS_CANCELADO = "cancelado"


class ContribuicaoError(Exception):
    pass


@dataclass
class PixContribuicaoResult:
    contribuicao_id: int
    txid: str
    qr_code_base64: str
    copia_cola_pix: str
    valor: float
    status: str
    contribuinte_nome: str
    categoria: str

    def asdict(self):
        return asdict(self)


def normalizar_cpf(cpf: str | None) -> str:
    return "".join(ch for ch in (cpf or "") if ch.isdigit())


def normalizar_texto(valor: str | None) -> str:
    return (valor or "").strip()


def moeda_para_decimal(valor: str | Decimal | float | int) -> Decimal:
    try:
        if isinstance(valor, Decimal):
            resultado = valor
        else:
            texto = str(valor).strip()
            if "," in texto:
                texto = texto.replace(".", "").replace(",", ".")
            resultado = Decimal(texto)
    except (InvalidOperation, ValueError):
        raise ContribuicaoError("Valor invalido.")

    if resultado <= 0:
        raise ContribuicaoError("Valor deve ser maior que zero.")
    return resultado.quantize(Decimal("0.01"))


def validar_cpf(cpf: str) -> bool:
    cpf = normalizar_cpf(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    dig1 = (soma * 10 % 11) % 10
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    dig2 = (soma * 10 % 11) % 10
    return cpf[-2:] == f"{dig1}{dig2}"


def ensure_categorias_padrao() -> None:
    existentes = {
        categoria.codigo
        for categoria in db.session.execute(db.select(CategoriaContribuicao)).scalars().all()
        if categoria.codigo
    }
    adicionou = False
    for codigo, descricao in CATEGORIAS_PADRAO:
        if codigo not in existentes:
            db.session.add(CategoriaContribuicao(codigo=codigo, descricao=descricao, ativo=True))
            adicionou = True
    db.session.flush()
    if adicionou:
        db.session.commit()


def listar_categorias(ativas=True):
    ensure_categorias_padrao()
    query = db.select(
        CategoriaContribuicao.id,
        CategoriaContribuicao.codigo,
        CategoriaContribuicao.descricao,
    )
    if ativas:
        query = query.where(CategoriaContribuicao.ativo.is_(True))
    rows = db.session.execute(query.order_by(CategoriaContribuicao.descricao.asc())).all()
    return [
        SimpleNamespace(id=row.id, codigo=row.codigo, descricao=row.descricao)
        for row in rows
        if row.codigo
    ]


def buscar_dizimista_por_cpf(cpf: str) -> Dizimista | None:
    return db.session.execute(
        db.select(Dizimista).where(Dizimista.cpf == normalizar_cpf(cpf))
    ).scalar_one_or_none()


def criar_ou_atualizar_dizimista(*, cpf: str, nome: str, telefone: str = "", whatsapp: str = "",
                                 email: str = "", comunidade_id: int | None = None, cep: str = "",
                                 endereco: str = "", numero: str = "", bairro: str = "",
                                 cidade: str = "") -> Dizimista:
    cpf = normalizar_cpf(cpf)
    if not validar_cpf(cpf):
        raise ContribuicaoError("CPF invalido.")

    nome = normalizar_texto(nome)
    if not nome:
        raise ContribuicaoError("Nome e obrigatorio.")

    dizimista = buscar_dizimista_por_cpf(cpf)
    if dizimista is None:
        dizimista = Dizimista(cpf=cpf)
        db.session.add(dizimista)

    dizimista.nome = nome.upper()
    dizimista.telefone = normalizar_cpf(telefone)
    dizimista.whatsapp = normalizar_cpf(whatsapp or telefone)
    dizimista.email = normalizar_texto(email).lower() or None
    dizimista.comunidade_id = int(comunidade_id) if comunidade_id else None
    dizimista.cep = normalizar_texto(cep) or None
    dizimista.endereco = normalizar_texto(endereco).upper() or None
    dizimista.numero = normalizar_texto(numero) or None
    dizimista.bairro = normalizar_texto(bairro).upper() or None
    dizimista.cidade = normalizar_texto(cidade).upper() or None
    dizimista.ativo = True
    db.session.flush()
    return dizimista


def _categoria_por_codigo(codigo: str) -> CategoriaContribuicao:
    ensure_categorias_padrao()
    categoria = db.session.execute(
        db.select(CategoriaContribuicao).where(CategoriaContribuicao.codigo == codigo)
    ).scalar_one_or_none()
    if categoria is None:
        raise ContribuicaoError("Tipo de contribuicao invalido.")
    return categoria


def _txid_from_charge(charge) -> str:
    raw_txid = "".join(ch for ch in (charge.external_id or "") if ch.isalnum()).upper()
    if len(raw_txid) >= 26:
        return raw_txid[:32]
    return uuid.uuid4().hex[:32].upper()


def gerar_pix_contribuicao(*, dizimista_id: int, categoria_codigo: str, valor, competencia: str = "",
                           descricao: str = "") -> PixContribuicaoResult:
    dizimista = db.session.get(Dizimista, dizimista_id)
    if dizimista is None:
        raise ContribuicaoError("Contribuinte nao encontrado.")

    categoria = _categoria_por_codigo(categoria_codigo)
    valor_decimal = moeda_para_decimal(valor)
    competencia = normalizar_texto(competencia) or datetime.utcnow().strftime("%Y-%m")

    gateway = get_pix_gateway()
    try:
        charge = gateway.create_charge(
            amount=valor_decimal,
            payer_name=dizimista.nome,
            payer_email=dizimista.email or "",
            payer_document=dizimista.cpf,
            description=f"{categoria.descricao} - {competencia}",
        )

        # Se o gateway não devolver QR Base64, gera localmente
        if not getattr(charge, "qr_code_base64", None) and charge.copia_cola_pix:
            charge.qr_code_base64 = _gerar_qr_code_base64(
                charge.copia_cola_pix
            )

    except TypeError:
        charge = gateway.create_charge(
            amount=valor_decimal,
            payer_name=dizimista.nome,
            payer_email=dizimista.email or "",
            description=f"{categoria.descricao} - {competencia}",
        )

    txid = _txid_from_charge(charge)
    contribuicao = Contribuicao(
        dizimista_id=dizimista.id,
        categoria_id=categoria.id,
        comunidade_id=dizimista.comunidade_id,
        competencia=competencia,
        valor=valor_decimal,
        descricao=normalizar_texto(descricao) or None,
        txid=txid,
        external_id=charge.external_id,
        qr_code_base64=charge.qr_code_base64,
        copia_cola_pix=charge.copia_cola_pix,
        chave_pix=current_app.config.get("PIX_CHAVE"),
        status=STATUS_PENDENTE,
        origem_pagamento="pix_auto",
        payload=charge.raw_response,
        banco_payload=json.dumps(charge.raw_response, ensure_ascii=False, default=str),
    )
    db.session.add(contribuicao)
    db.session.flush()
    db.session.commit()

    return PixContribuicaoResult(
        contribuicao_id=contribuicao.id,
        txid=contribuicao.txid,
        qr_code_base64=contribuicao.qr_code_base64 or "",
        copia_cola_pix=contribuicao.copia_cola_pix or "",
        valor=float(contribuicao.valor),
        status=contribuicao.status,
        contribuinte_nome=dizimista.nome,
        categoria=categoria.descricao,
    )


def buscar_contribuicao_por_txid(txid: str) -> Contribuicao | None:
    return db.session.execute(
        db.select(Contribuicao).where(func.upper(Contribuicao.txid) == (txid or "").upper())
    ).scalar_one_or_none()


def confirmar_pagamento_pix(pix: dict) -> Contribuicao | None:
    txid = (pix.get("txid") or "").strip().upper()
    if not txid:
        return None

    contribuicao = buscar_contribuicao_por_txid(txid)
    if contribuicao is None:
        return None
    if contribuicao.status == STATUS_PAGO:
        return contribuicao

    contribuicao.status = STATUS_PAGO

    contribuicao.data_pagamento = datetime.utcnow()

    
    endtoend = None

    if pix.get("pix"):
        endtoend = pix["pix"][0].get("endToEndId")

    if not endtoend:
        endtoend = pix.get("endToEndId")

    if not endtoend:
        endtoend = pix.get("endtoendid")

    contribuicao.endtoendid = endtoend    

    contribuicao.codigo_autenticacao = (
        pix.get("codigoAutenticacao")
        or pix.get("autenticacao")
    )

    contribuicao.pagador = (
        pix.get("pagador", {}).get("nome")
        if isinstance(pix.get("pagador"), dict)
        else pix.get("pagador")
    )

    contribuicao.cpf_pagador = (
        pix.get("pagador", {}).get("cpf")
        if isinstance(pix.get("pagador"), dict)
        else pix.get("cpf") or pix.get("cpfCnpj")
    )

    contribuicao.payload = pix

    contribuicao.banco_payload = json.dumps(
        pix,
        ensure_ascii=False,
        default=str
    )

    #try:

       #emitir_recibo(contribuicao)

    #except Exception as e:

        #current_app.logger.exception(e)

    db.session.commit()

    return contribuicao

def verificar_contribuicoes_pendentes() -> int:

    gateway = get_pix_gateway()

    limite = datetime.utcnow() - timedelta(days=3)

    pendentes = db.session.execute(

        db.select(Contribuicao).where(

            Contribuicao.status == STATUS_PENDENTE,

            Contribuicao.data_geracao >= limite,

            Contribuicao.txid.isnot(None)

        )

    ).scalars().all()

    confirmadas = 0

    for contribuicao in pendentes:

        try:

            data = gateway.consultar_cobranca(
                contribuicao.txid
            )

        except Exception:

            current_app.logger.exception(
                "Erro consultando TXID %s",
                contribuicao.txid
            )

            continue

        if not data:
            continue

        status = (data.get("status") or "").upper()

        # cobrança concluída
        if status in ("CONCLUIDA", "LIQUIDADA"):

            data.setdefault(
                "txid",
                contribuicao.txid
            )

            confirmar_pagamento_pix(data)

            confirmadas += 1

            continue

        # Sicredi retorna pagamento dentro de pix[]
        pixs = data.get("pix", [])

        if pixs:

            for pix in pixs:

                pix.setdefault(
                    "txid",
                    contribuicao.txid
                )

                confirmar_pagamento_pix(pix)

                print(
                    "PIX CONFIRMADO:",
                    contribuicao.txid
                )                

                confirmadas += 1

                break

    if confirmadas:

        db.session.commit()

    return confirmadas


def emitir_recibo(contribuicao: Contribuicao) -> ReciboContribuicao:
    try:

        if hasattr(contribuicao, "recibo") and contribuicao.recibo:
            return contribuicao.recibo

    except Exception:
        pass
        
    numero = f"CON-{datetime.utcnow():%Y%m%d}-{contribuicao.id:06d}"
    recibo = ReciboContribuicao(contribuicao_id=contribuicao.id, numero=numero)
    db.session.add(recibo)
    db.session.flush()
    return recibo


def consulta_relatorio(args):
    query = db.select(Contribuicao).where(Contribuicao.status == STATUS_PAGO)

    if not session.get("administrador"):

        query = query.where(
            Contribuicao.comunidade_id ==
            session["comunidade_id"]
        )    

    inicio = args.get("inicio")
    fim = args.get("fim")
    if inicio:
        query = query.where(Contribuicao.data_pagamento >= datetime.strptime(inicio, "%Y-%m-%d"))
    if fim:
        query = query.where(Contribuicao.data_pagamento < datetime.strptime(fim, "%Y-%m-%d") + timedelta(days=1))
    if args.get("comunidade_id"):
        query = query.where(Contribuicao.comunidade_id == int(args["comunidade_id"]))
    if args.get("dizimista_id"):
        query = query.where(Contribuicao.dizimista_id == int(args["dizimista_id"]))
    if args.get("categoria_id"):
        query = query.where(Contribuicao.categoria_id == int(args["categoria_id"]))
    if args.get("mes"):
        query = query.where(extract("month", Contribuicao.data_pagamento) == int(args["mes"]))
    if args.get("ano"):
        query = query.where(extract("year", Contribuicao.data_pagamento) == int(args["ano"]))

    return db.session.execute(query.order_by(Contribuicao.data_pagamento.desc())).scalars().all()


def totais_dashboard():

    ensure_categorias_padrao()

    query = (
        db.select(
            CategoriaContribuicao.codigo,
            CategoriaContribuicao.descricao,
            func.coalesce(func.sum(Contribuicao.valor), 0)
        )
        .join(
            Contribuicao,
            Contribuicao.categoria_id == CategoriaContribuicao.id,
            isouter=True
        )
        .where(
            db.or_(
                Contribuicao.status == STATUS_PAGO,
                Contribuicao.id.is_(None)
            )
        )
    )

    # filtrar por comunidade
    if not session.get("administrador"):

        query = query.where(
            db.or_(
                Contribuicao.comunidade_id == session["comunidade_id"],
                Contribuicao.id.is_(None)
            )
        )

    rows = db.session.execute(

        query.group_by(
            CategoriaContribuicao.codigo,
            CategoriaContribuicao.descricao
        )

    ).all()

    por_codigo = {
        row[0]: Decimal(row[2] or 0)
        for row in rows
    }

    return {

        "dizimo": por_codigo.get("dizimo", Decimal("0.00")),

        "doacao": por_codigo.get("doacao", Decimal("0.00")),

        "oferta": por_codigo.get("oferta", Decimal("0.00")),

        "campanha": por_codigo.get("campanha", Decimal("0.00")),

        "construcao": por_codigo.get("construcao", Decimal("0.00")),

        "evangelizacao": por_codigo.get("evangelizacao", Decimal("0.00")),

        "geral": sum(
            por_codigo.values(),
            Decimal("0.00")
        )

    }

def ranking_por_comunidade(limit=20):

    query = (
        db.select(
            Comunidade.nome,
            func.count(Contribuicao.id),
            func.coalesce(func.sum(Contribuicao.valor),0)
        )
        .join(
            Contribuicao,
            Contribuicao.comunidade_id == Comunidade.id
        )
        .where(
            Contribuicao.status == STATUS_PAGO
        )
    )

    if not session.get("administrador"):

        query = query.where(
            Contribuicao.comunidade_id ==
            session["comunidade_id"]
        )

    return db.session.execute(

        query.group_by(
            Comunidade.nome
        )

        .order_by(
            func.sum(
                Contribuicao.valor
            ).desc()
        )

        .limit(limit)

    ).all()


def ranking_por_contribuinte(limit=20):

    query = (
        db.select(
            Dizimista.id,
            Dizimista.nome,
            func.count(Contribuicao.id),
            func.coalesce(func.sum(Contribuicao.valor),0)
        )
        .join(
            Contribuicao,
            Contribuicao.dizimista_id == Dizimista.id
        )
        .where(
            Contribuicao.status == STATUS_PAGO
        )
    )

    if not session.get("administrador"):

        query = query.where(
            Dizimista.comunidade_id ==
            session["comunidade_id"]
        )

    return db.session.execute(

        query.group_by(
            Dizimista.id,
            Dizimista.nome
        )

        .order_by(
            func.sum(
                Contribuicao.valor
            ).desc()
        )

        .limit(limit)

    ).all()


def historico_dizimista(dizimista_id: int):
    dizimista = db.session.get(Dizimista, dizimista_id)
    if dizimista is None:
        raise ContribuicaoError("Contribuinte nao encontrado.")
    contribuicoes = db.session.execute(
        db.select(Contribuicao)
        .where(Contribuicao.dizimista_id == dizimista.id)
        .order_by(Contribuicao.data_geracao.desc())
    ).scalars().all()
    return dizimista, contribuicoes


def demonstrativo_anual(dizimista_id: int, ano: int):
    dizimista, _ = historico_dizimista(dizimista_id)
    contribuicoes = db.session.execute(
        db.select(Contribuicao)
        .where(
            Contribuicao.dizimista_id == dizimista.id,
            Contribuicao.status == STATUS_PAGO,
            extract("year", Contribuicao.data_pagamento) == ano,
        )
        .order_by(Contribuicao.data_pagamento.asc())
    ).scalars().all()
    total = sum((item.valor for item in contribuicoes), Decimal("0.00"))
    return dizimista, contribuicoes, total


def gerar_excel(contribuicoes) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Contribuicoes"
    ws.append(["Data", "Contribuinte", "CPF", "Comunidade", "Tipo", "Competencia", "Valor", "TXID"])
    for item in contribuicoes:
        ws.append([
            item.data_pagamento.strftime("%d/%m/%Y") if item.data_pagamento else "",
            item.dizimista.nome,
            item.dizimista.cpf,
            item.comunidade.nome if item.comunidade else "",
            item.categoria.descricao,
            item.competencia,
            float(item.valor),
            item.txid,
        ])
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def gerar_pdf_relatorio(contribuicoes, titulo="Relatorio de Contribuicoes") -> BytesIO:
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4)
    styles = getSampleStyleSheet()
    data = [["Data", "Contribuinte", "Comunidade", "Tipo", "Valor"]]
    total = Decimal("0.00")
    for item in contribuicoes:
        total += item.valor
        data.append([
            item.data_pagamento.strftime("%d/%m/%Y") if item.data_pagamento else "",
            item.dizimista.nome[:28],
            (item.comunidade.nome if item.comunidade else "")[:20],
            item.categoria.descricao,
            f"R$ {item.valor:.2f}",
        ])
    data.append(["", "", "", "Total", f"R$ {total:.2f}"])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#198754")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    doc.build([Paragraph(titulo, styles["Title"]), Spacer(1, 12), table])
    output.seek(0)
    return output


def verificar_contribuicao(contribuicao_id):

    contribuicao = Contribuicao.query.get(contribuicao_id)

    gateway = get_pix_gateway()

    retorno = gateway.consultar_cobranca(
        contribuicao.txid
    )

    if not retorno:
        return False

    # pagamento individual

    if retorno.get("status") in [
        "CONCLUIDA",
        "LIQUIDADA"
    ]:

        contribuicao.status="pago"
        contribuicao.data_pagamento=datetime.now()
        contribuicao.endtoendid=retorno.get("endToEndId")
        contribuicao.codigo_autenticacao=retorno.get("codigoAutenticacao")
        contribuicao.payload=retorno

        db.session.commit()

        return True

    # pagamento retornando em pix[]

    for pix in retorno.get("pix",[]):

        contribuicao.status="pago"
        contribuicao.data_pagamento=datetime.now()
        contribuicao.endtoendid=pix.get("endToEndId")
        contribuicao.payload=pix

        db.session.commit()

        return True

    return False


from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Spacer,
    Paragraph,
    Table,
    TableStyle
)

def gerar_pdf_comprovante(contribuicao):

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()

    titulo = styles["Heading1"]
    titulo.alignment = TA_CENTER

    normal = styles["Normal"]

    elementos = []

    elementos.append(
        Paragraph(
            "<b>PARÓQUIA NOSSA SENHORA APARECIDA</b>",
            titulo
        )
    )

    elementos.append(
        Paragraph(
            "Comprovante Oficial de Contribuição",
            titulo
        )
    )

    elementos.append(
        Spacer(1,20)
    )

    nome = "-"
    cpf = "-"
    comunidade = "-"
    categoria = "-"
    competencia = "-"
    txid = "-"
    endtoendid = "-"
    data_pagamento = "-"

    if contribuicao.dizimista:
        nome = contribuicao.dizimista.nome or "-"
        cpf = contribuicao.dizimista.cpf or "-"

    if contribuicao.comunidade:
        comunidade = contribuicao.comunidade.nome or "-"

    if contribuicao.categoria:
        categoria = contribuicao.categoria.descricao or "-"

    if contribuicao.competencia:
        competencia = contribuicao.competencia

    if contribuicao.txid:
        txid = contribuicao.txid

    if contribuicao.endtoendid:
        endtoendid = contribuicao.endtoendid

    if contribuicao.data_pagamento:
        data_pagamento = contribuicao.data_pagamento.strftime(
            "%d/%m/%Y %H:%M"
        )

    dados = [

        ["Nome", nome],

        ["CPF", cpf],

        ["Comunidade", comunidade],

        ["Categoria", categoria],

        ["Competência", competencia],

        ["Valor", f"R$ {float(contribuicao.valor):,.2f}"],

        ["TXID", txid],

        ["EndToEndId", endtoendid],

        ["Data Pagamento", data_pagamento]

    ]

    tabela = Table(
        dados,
        colWidths=[120,350]
    )

    tabela.setStyle(

        TableStyle([

            ("GRID",(0,0),(-1,-1),1,colors.black),

            ("BACKGROUND",(0,0),(0,-1),colors.lightgrey),

            ("FONTNAME",(0,0),(-1,-1),"Helvetica"),

            ("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),

            ("BOTTOMPADDING",(0,0),(-1,-1),8),

            ("TOPPADDING",(0,0),(-1,-1),8),

        ])

    )

    elementos.append(tabela)

    elementos.append(
        Spacer(1,20)
    )

    elementos.append(

        Paragraph(

            """
            Recebemos a presente contribuição destinada às atividades pastorais,
            evangelização, manutenção da Igreja e obras sociais.

            <br/><br/>

            "Cada um contribua segundo tiver decidido em seu coração,
            não com tristeza ou por obrigação,
            pois Deus ama quem dá com alegria."

            <br/><br/>

            <b>2 Coríntios 9,7</b>

            """,

            normal

        )

    )

    elementos.append(
        Spacer(1,30)
    )

    elementos.append(

        Paragraph(

            "<b>Paróquia Nossa Senhora Aparecida</b>",

            titulo

        )

    )

    doc.build(elementos)

    buffer.seek(0)

    return buffer