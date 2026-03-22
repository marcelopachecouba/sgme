import base64
import calendar
import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask_login import current_user
from sqlalchemy import func

from extensions import db
from financeiro.models import (
    CategoriaFinanceira,
    CentroCusto,
    ContaCorrente,
    Duplicata,
    DuplicataParcela,
    ExtratoImportado,
    ExtratoPadrao,
    LancamentoFinanceiro,
    SubcategoriaFinanceira,
)

TIPOS_LANCAMENTO = ("RECEBER", "PAGAR")
STATUS_LANCAMENTO = ("ABERTO", "PAGO")
ORIGENS_LANCAMENTO = ("MANUAL", "IMPORTACAO")
STATUS_CONCILIACAO = ("SIM", "NAO")


def _query(model):
    return model.query.filter_by(id_paroquia=current_user.id_paroquia)


def parse_date(value):
    raw = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError("Data invalida.")


def parse_decimal(value):
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Valor invalido.")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Valor invalido.") from exc


def money(value):
    amount = Decimal(value or 0).quantize(Decimal("0.01"))
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    inteiro, fracao = f"{amount:.2f}".split(".")
    grupos = []
    while inteiro:
        grupos.append(inteiro[-3:])
        inteiro = inteiro[:-3]
    return f"{sign}R$ {'.'.join(reversed(grupos))},{fracao}"


def _normalized(text):
    raw = (text or "").strip().lower()
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", raw).split())


def _effect(tipo, valor):
    valor = Decimal(valor or 0).quantize(Decimal("0.01"))
    return valor if tipo == "RECEBER" else -valor


def _sync_balance(lancamento, status_anterior=None):
    conta = _query(ContaCorrente).filter_by(id=lancamento.conta_corrente_id).first()
    if not conta:
        return
    delta = Decimal("0.00")
    if status_anterior == "PAGO":
        delta -= _effect(lancamento.tipo, lancamento.valor)
    if lancamento.status == "PAGO":
        delta += _effect(lancamento.tipo, lancamento.valor)
    if delta:
        conta.saldo_atual = Decimal(conta.saldo_atual or 0) + delta


def _find(model, item_id):
    if not item_id:
        return None
    return _query(model).filter_by(id=int(item_id)).first()


def _find_pattern(descricao):
    desc = _normalized(descricao)
    if not desc:
        return None
    padroes = _query(ExtratoPadrao).order_by(func.length(ExtratoPadrao.descricao_padrao).desc()).all()
    for padrao in padroes:
        trecho = _normalized(padrao.descricao_padrao)
        if trecho and trecho in desc:
            return padrao
    return None


def suggest_category(descricao):
    padrao = _find_pattern(descricao)
    if padrao:
        return {
            "categoria_id": padrao.categoria_id,
            "categoria_nome": padrao.categoria.nome if padrao.categoria else "",
            "subcategoria_id": padrao.subcategoria_id,
            "subcategoria_nome": padrao.subcategoria.nome if padrao.subcategoria else "",
            "centro_custo_id": padrao.centro_custo_id,
            "centro_custo_nome": padrao.centro_custo.nome if padrao.centro_custo else "",
            "origem": "extrato_padrao",
        }

    descricao_norm = _normalized(descricao)
    historico = []
    if descricao_norm:
        candidatos = _query(LancamentoFinanceiro).filter(LancamentoFinanceiro.descricao.ilike(f"%{descricao}%")).order_by(LancamentoFinanceiro.id.desc()).limit(10).all()
        for item in candidatos:
            if _normalized(item.descricao) and (_normalized(item.descricao) in descricao_norm or descricao_norm in _normalized(item.descricao)):
                historico.append(item)
    if historico:
        item = historico[0]
        return {
            "categoria_id": item.categoria_id,
            "categoria_nome": item.categoria.nome if item.categoria else "",
            "subcategoria_id": item.subcategoria_id,
            "subcategoria_nome": item.subcategoria.nome if item.subcategoria else "",
            "centro_custo_id": item.centro_custo_id,
            "centro_custo_nome": item.centro_custo.nome if item.centro_custo else "",
            "origem": "historico",
        }
    return None


def get_dashboard_totals(centro_custo_id=None, conta_id=None, status=None):
    query = _query(LancamentoFinanceiro)
    if centro_custo_id:
        query = query.filter_by(centro_custo_id=int(centro_custo_id))
    if conta_id:
        query = query.filter_by(conta_corrente_id=int(conta_id))
    if status:
        query = query.filter_by(status=status)
    linhas = query.all()
    totais = {
        "saldo_geral": Decimal(_query(ContaCorrente).with_entities(func.coalesce(func.sum(ContaCorrente.saldo_atual), 0)).scalar() or 0),
        "total_pagar": Decimal("0.00"),
        "total_receber": Decimal("0.00"),
        "pago": Decimal("0.00"),
    }
    for item in linhas:
        if item.tipo == "PAGAR" and item.status != "PAGO":
            totais["total_pagar"] += Decimal(item.valor)
        if item.tipo == "RECEBER" and item.status != "PAGO":
            totais["total_receber"] += Decimal(item.valor)
        if item.status == "PAGO":
            totais["pago"] += Decimal(item.valor)
    return {k: Decimal(v).quantize(Decimal("0.01")) for k, v in totais.items()}


def list_accounts():
    return [
        {"id": item.id, "nome": item.nome, "saldo_atual": float(item.saldo_atual or 0), "saldo_label": money(item.saldo_atual)}
        for item in _query(ContaCorrente).order_by(ContaCorrente.nome.asc()).all()
    ]


def save_account(account_id, nome, saldo_atual):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome da conta.")
    saldo = parse_decimal(saldo_atual)
    conta = _find(ContaCorrente, account_id) if account_id else ContaCorrente(id_paroquia=current_user.id_paroquia)
    if not conta:
        raise ValueError("Conta nao encontrada.")
    conta.nome = nome
    conta.saldo_atual = saldo
    db.session.add(conta)
    db.session.commit()
    return conta


def delete_account(account_id):
    conta = _find(ContaCorrente, account_id)
    if not conta:
        raise ValueError("Conta nao encontrada.")
    if _query(LancamentoFinanceiro).filter_by(conta_corrente_id=conta.id).first() or _query(ExtratoImportado).filter_by(conta_corrente_id=conta.id).first():
        raise ValueError("Conta possui movimentacoes vinculadas.")
    db.session.delete(conta)
    db.session.commit()


def list_centros():
    return [{"id": item.id, "nome": item.nome} for item in _query(CentroCusto).order_by(CentroCusto.nome.asc()).all()]


def save_centro(centro_id, nome):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o centro de custo.")
    centro = _find(CentroCusto, centro_id) if centro_id else CentroCusto(id_paroquia=current_user.id_paroquia)
    if not centro:
        raise ValueError("Centro de custo nao encontrado.")
    centro.nome = nome
    db.session.add(centro)
    db.session.commit()
    return centro


def list_categories():
    categorias = _query(CategoriaFinanceira).order_by(CategoriaFinanceira.nome.asc()).all()
    dados = []
    for item in categorias:
        dados.append({
            "id": item.id,
            "nome": item.nome,
            "subcategorias": ", ".join(sub.nome for sub in item.subcategorias) if item.subcategorias else "",
        })
    return dados


def list_subcategories():
    return [
        {"id": item.id, "nome": item.nome, "categoria_id": item.categoria_id, "categoria": item.categoria.nome if item.categoria else ""}
        for item in _query(SubcategoriaFinanceira).order_by(SubcategoriaFinanceira.nome.asc()).all()
    ]


def save_category(category_id, nome):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe a categoria.")
    categoria = _find(CategoriaFinanceira, category_id) if category_id else CategoriaFinanceira(id_paroquia=current_user.id_paroquia)
    if not categoria:
        raise ValueError("Categoria nao encontrada.")
    categoria.nome = nome
    db.session.add(categoria)
    db.session.commit()
    return categoria


def save_subcategory(subcategory_id, nome, categoria_id):
    nome = (nome or "").strip()
    categoria = _find(CategoriaFinanceira, categoria_id)
    if not nome or not categoria:
        raise ValueError("Informe nome e categoria validos.")
    sub = _find(SubcategoriaFinanceira, subcategory_id) if subcategory_id else SubcategoriaFinanceira(id_paroquia=current_user.id_paroquia)
    if not sub:
        raise ValueError("Subcategoria nao encontrada.")
    sub.nome = nome
    sub.categoria_id = categoria.id
    db.session.add(sub)
    db.session.commit()
    return sub


def list_lancamentos(data_inicial=None, data_final=None, conta_id=None, centro_custo_id=None, status=None):
    query = _query(LancamentoFinanceiro)
    if data_inicial:
        query = query.filter(LancamentoFinanceiro.data >= parse_date(data_inicial))
    if data_final:
        query = query.filter(LancamentoFinanceiro.data <= parse_date(data_final))
    if conta_id:
        query = query.filter_by(conta_corrente_id=int(conta_id))
    if centro_custo_id:
        query = query.filter_by(centro_custo_id=int(centro_custo_id))
    if status:
        query = query.filter_by(status=status)
    itens = query.order_by(LancamentoFinanceiro.data.desc(), LancamentoFinanceiro.id.desc()).all()
    return [
        {
            "id": item.id,
            "data": item.data.strftime("%Y-%m-%d"),
            "descricao": item.descricao,
            "valor": float(item.valor),
            "valor_label": money(item.valor),
            "tipo": item.tipo,
            "conta_corrente_id": item.conta_corrente_id,
            "conta": item.conta_corrente.nome if item.conta_corrente else "",
            "categoria_id": item.categoria_id,
            "categoria": item.categoria.nome if item.categoria else "",
            "subcategoria_id": item.subcategoria_id or "",
            "subcategoria": item.subcategoria.nome if item.subcategoria else "",
            "centro_custo_id": item.centro_custo_id,
            "centro_custo": item.centro_custo.nome if item.centro_custo else "",
            "status": item.status,
            "origem": item.origem,
        }
        for item in itens
    ]


def save_lancamento(lancamento_id, payload):
    conta = _find(ContaCorrente, payload.get("conta_corrente_id"))
    categoria = _find(CategoriaFinanceira, payload.get("categoria_id"))
    centro = _find(CentroCusto, payload.get("centro_custo_id"))
    sub = _find(SubcategoriaFinanceira, payload.get("subcategoria_id")) if payload.get("subcategoria_id") else None
    if not conta or not categoria or not centro:
        raise ValueError("Conta, categoria e centro de custo sao obrigatorios.")
    if sub and sub.categoria_id != categoria.id:
        raise ValueError("Subcategoria nao pertence a categoria.")

    lancamento = _find(LancamentoFinanceiro, lancamento_id) if lancamento_id else LancamentoFinanceiro(id_paroquia=current_user.id_paroquia)
    if not lancamento:
        raise ValueError("Lancamento nao encontrado.")

    descricao = (payload.get("descricao") or "").strip()
    if not descricao:
        raise ValueError("Descricao do lancamento e obrigatoria.")

    snapshot = None
    if lancamento.id:
        snapshot = {
            "conta_corrente_id": lancamento.conta_corrente_id,
            "tipo": lancamento.tipo,
            "valor": Decimal(lancamento.valor or 0).quantize(Decimal("0.01")),
            "status": lancamento.status,
        }

    if snapshot and snapshot["status"] == "PAGO":
        conta_antiga = _find(ContaCorrente, snapshot["conta_corrente_id"])
        if conta_antiga:
            conta_antiga.saldo_atual = Decimal(conta_antiga.saldo_atual or 0) - _effect(snapshot["tipo"], snapshot["valor"])

    lancamento.data = parse_date(payload.get("data"))
    lancamento.descricao = descricao
    lancamento.valor = parse_decimal(payload.get("valor"))
    lancamento.tipo = payload.get("tipo") or "PAGAR"
    lancamento.conta_corrente_id = conta.id
    lancamento.categoria_id = categoria.id
    lancamento.subcategoria_id = sub.id if sub else None
    lancamento.centro_custo_id = centro.id
    lancamento.status = payload.get("status") or "ABERTO"
    lancamento.origem = payload.get("origem") or "MANUAL"

    db.session.add(lancamento)
    db.session.flush()

    if lancamento.status == "PAGO":
        conta_nova = _find(ContaCorrente, lancamento.conta_corrente_id)
        if conta_nova:
            conta_nova.saldo_atual = Decimal(conta_nova.saldo_atual or 0) + _effect(lancamento.tipo, lancamento.valor)

    if lancamento.duplicata_parcela:
        lancamento.duplicata_parcela.status = lancamento.status

    db.session.commit()
    return lancamento


def delete_lancamento(lancamento_id):
    lancamento = _find(LancamentoFinanceiro, lancamento_id)
    if not lancamento:
        raise ValueError("Lancamento nao encontrado.")
    if lancamento.status == "PAGO":
        conta = _find(ContaCorrente, lancamento.conta_corrente_id)
        if conta:
            conta.saldo_atual = Decimal(conta.saldo_atual or 0) - _effect(lancamento.tipo, lancamento.valor)
    if lancamento.duplicata_parcela:
        lancamento.duplicata_parcela.status = "ABERTO"
    db.session.delete(lancamento)
    db.session.commit()


def toggle_paid(lancamento_id):
    lancamento = _find(LancamentoFinanceiro, lancamento_id)
    if not lancamento:
        raise ValueError("Lancamento nao encontrado.")
    status_anterior = lancamento.status
    lancamento.status = "PAGO" if lancamento.status != "PAGO" else "ABERTO"
    if lancamento.duplicata_parcela:
        lancamento.duplicata_parcela.status = lancamento.status
    _sync_balance(lancamento, status_anterior=status_anterior)
    db.session.commit()
    return lancamento


def list_duplicatas():
    itens = _query(Duplicata).order_by(Duplicata.id.desc()).all()
    return [
        {"id": item.id, "descricao": item.descricao, "valor_total": float(item.valor_total), "valor_total_label": money(item.valor_total), "quantidade_parcelas": item.quantidade_parcelas, "tipo": item.tipo}
        for item in itens
    ]


def list_parcelas():
    itens = _query(DuplicataParcela).order_by(DuplicataParcela.data_vencimento.asc(), DuplicataParcela.numero_parcela.asc()).all()
    return [
        {"id": item.id, "duplicata_id": item.duplicata_id, "duplicata": item.duplicata.descricao if item.duplicata else "", "numero_parcela": item.numero_parcela, "total_parcelas": item.duplicata.quantidade_parcelas if item.duplicata else 0, "data_vencimento": item.data_vencimento.strftime("%Y-%m-%d"), "valor": float(item.valor), "valor_label": money(item.valor), "status": item.status}
        for item in itens
    ]


def save_duplicata(duplicata_id, payload):
    descricao = (payload.get("descricao") or "").strip()
    if not descricao:
        raise ValueError("Informe a descricao da duplicata.")
    tipo = payload.get("tipo") or "PAGAR"
    quantidade = int(payload.get("quantidade_parcelas") or 1)
    valor_total = parse_decimal(payload.get("valor_total"))
    primeiro_vencimento = parse_date(payload.get("primeiro_vencimento"))
    duplicata = _find(Duplicata, duplicata_id) if duplicata_id else Duplicata(id_paroquia=current_user.id_paroquia)
    if not duplicata:
        raise ValueError("Duplicata nao encontrada.")
    if duplicata.id and any(p.status == "PAGO" for p in duplicata.parcelas):
        raise ValueError("Nao edite duplicatas com parcelas pagas.")
    duplicata.descricao = descricao
    duplicata.valor_total = valor_total
    duplicata.quantidade_parcelas = quantidade
    duplicata.tipo = tipo
    db.session.add(duplicata)
    db.session.flush()
    if duplicata.id:
        for parcela in list(duplicata.parcelas):
            vinculado = _query(LancamentoFinanceiro).filter_by(duplicata_parcela_id=parcela.id).first()
            if vinculado:
                raise ValueError("Existe lancamento vinculado a esta duplicata. Exclua-o antes de alterar parcelas.")
            db.session.delete(parcela)
        db.session.flush()
    base = (valor_total / quantidade).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    acumulado = Decimal("0.00")
    for numero in range(1, quantidade + 1):
        valor = base if numero < quantidade else (valor_total - acumulado).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        acumulado += valor
        db.session.add(DuplicataParcela(duplicata_id=duplicata.id, numero_parcela=numero, data_vencimento=_add_months(primeiro_vencimento, numero - 1), valor=valor, status="ABERTO", id_paroquia=current_user.id_paroquia))
    db.session.commit()
    return duplicata


def _add_months(data_base, quantidade):
    mes_total = data_base.month - 1 + quantidade
    ano = data_base.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(data_base.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def delete_duplicata(duplicata_id):
    duplicata = _find(Duplicata, duplicata_id)
    if not duplicata:
        raise ValueError("Duplicata nao encontrada.")
    if _query(LancamentoFinanceiro).join(DuplicataParcela, LancamentoFinanceiro.duplicata_parcela_id == DuplicataParcela.id).filter(DuplicataParcela.duplicata_id == duplicata.id).first():
        raise ValueError("Duplicata possui lancamentos vinculados.")
    db.session.delete(duplicata)
    db.session.commit()


def baixar_parcela(parcela_id):
    parcela = _find(DuplicataParcela, parcela_id)
    if not parcela:
        raise ValueError("Parcela nao encontrada.")
    lancamento = _query(LancamentoFinanceiro).filter_by(duplicata_parcela_id=parcela.id).first()
    if not lancamento:
        raise ValueError("Gere um lancamento para a parcela antes da baixa.")
    status_anterior = lancamento.status
    lancamento.status = "PAGO"
    parcela.status = "PAGO"
    _sync_balance(lancamento, status_anterior=status_anterior)
    db.session.commit()
    return parcela


def gerar_lancamento_parcela(parcela_id, payload):
    parcela = _find(DuplicataParcela, parcela_id)
    if not parcela:
        raise ValueError("Parcela nao encontrada.")
    if _query(LancamentoFinanceiro).filter_by(duplicata_parcela_id=parcela.id).first():
        raise ValueError("Esta parcela ja possui lancamento.")
    payload = dict(payload)
    payload["data"] = parcela.data_vencimento.strftime("%Y-%m-%d")
    payload["descricao"] = f"{parcela.duplicata.descricao} - Parcela {parcela.numero_parcela}/{parcela.duplicata.quantidade_parcelas}"
    payload["valor"] = str(parcela.valor)
    payload["tipo"] = parcela.duplicata.tipo
    payload["status"] = parcela.status
    payload["origem"] = "MANUAL"
    lancamento = save_lancamento(None, payload)
    lancamento.duplicata_parcela_id = parcela.id
    db.session.commit()
    return lancamento


def list_extrato(data_inicial=None, data_final=None, conta_id=None, centro_custo_id=None, status=None):
    query = _query(ExtratoImportado)
    if data_inicial:
        query = query.filter(ExtratoImportado.data >= parse_date(data_inicial))
    if data_final:
        query = query.filter(ExtratoImportado.data <= parse_date(data_final))
    if conta_id:
        query = query.filter_by(conta_corrente_id=int(conta_id))
    if status == "SIM":
        query = query.filter_by(conciliado="SIM")
    elif status == "NAO":
        query = query.filter_by(conciliado="NAO")
    itens = query.order_by(ExtratoImportado.data.desc(), ExtratoImportado.id.desc()).all()
    if centro_custo_id:
        itens = [item for item in itens if item.lancamento_financeiro and item.lancamento_financeiro.centro_custo_id == int(centro_custo_id)]
    dados = []
    for item in itens:
        sugestao = suggest_category(item.descricao)
        dados.append({
            "id": item.id,
            "data": item.data.strftime("%Y-%m-%d"),
            "descricao": item.descricao,
            "valor": float(item.valor),
            "valor_label": money(item.valor),
            "conta_corrente_id": item.conta_corrente_id,
            "conta": item.conta_corrente.nome if item.conta_corrente else "",
            "conciliado": item.conciliado,
            "lancamento_financeiro_id": item.lancamento_financeiro_id or "",
            "lancamento": item.lancamento_financeiro.descricao if item.lancamento_financeiro else "",
            "sugestao": sugestao["categoria_nome"] if sugestao else "",
        })
    return dados


def _exists_duplicate_extrato(data_item, descricao, valor, conta_id):
    return _query(ExtratoImportado).filter_by(data=data_item, descricao=(descricao or "").strip(), valor=Decimal(valor).quantize(Decimal("0.01")), conta_corrente_id=conta_id).first() is not None


def _create_imported_launch(extrato):
    padrao = _find_pattern(extrato.descricao)
    if not padrao:
        return None
    tipo = "RECEBER" if Decimal(extrato.valor) >= 0 else "PAGAR"
    valor = abs(Decimal(extrato.valor))
    lancamento = LancamentoFinanceiro(
        data=extrato.data,
        descricao=extrato.descricao,
        valor=valor,
        tipo=tipo,
        conta_corrente_id=extrato.conta_corrente_id,
        categoria_id=padrao.categoria_id,
        subcategoria_id=padrao.subcategoria_id,
        centro_custo_id=padrao.centro_custo_id,
        status="PAGO",
        origem="IMPORTACAO",
        id_paroquia=current_user.id_paroquia,
    )
    db.session.add(lancamento)
    db.session.flush()
    _sync_balance(lancamento, status_anterior=None)
    extrato.conciliado = "SIM"
    extrato.lancamento_financeiro_id = lancamento.id
    return lancamento


def save_extrato_manual(data_item, descricao, valor, conta_id):
    conta = _find(ContaCorrente, conta_id)
    if not conta:
        raise ValueError("Conta nao encontrada.")
    data_item = parse_date(data_item)
    valor = parse_decimal(valor)
    if _exists_duplicate_extrato(data_item, descricao, valor, conta.id):
        raise ValueError("Este item de extrato ja foi importado anteriormente.")
    extrato = ExtratoImportado(data=data_item, descricao=(descricao or "").strip(), valor=valor, conta_corrente_id=conta.id, conciliado="NAO", id_paroquia=current_user.id_paroquia)
    db.session.add(extrato)
    db.session.flush()
    _create_imported_launch(extrato)
    db.session.commit()
    return extrato


def _decode_upload(contents):
    _, content_string = contents.split(",", 1)
    return base64.b64decode(content_string)


def import_statement(contents, filename, conta_id):
    conta = _find(ContaCorrente, conta_id)
    if not conta:
        raise ValueError("Conta nao encontrada.")
    if not contents or not filename:
        raise ValueError("Selecione um arquivo valido.")
    arquivo = _decode_upload(contents)
    registros = []
    nome = filename.lower()
    if nome.endswith(".csv"):
        texto = arquivo.decode("utf-8-sig")
        amostra = texto[:2048]
        try:
            dialect = csv.Sniffer().sniff(amostra, delimiters=",;")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"
        leitor = csv.DictReader(io.StringIO(texto), dialect=dialect)
        for linha in leitor:
            normalizada = {str(k or "").strip().lower(): (v or "").strip() for k, v in linha.items()}
            data_item = normalizada.get("data") or normalizada.get("date")
            descricao = normalizada.get("descricao") or normalizada.get("historico") or normalizada.get("memo")
            valor = normalizada.get("valor") or normalizada.get("amount")
            if data_item and descricao and valor:
                registros.append((data_item, descricao, valor))
    elif nome.endswith(".ofx"):
        texto = arquivo.decode("utf-8-sig", errors="ignore")
        padrao = re.compile(r"<STMTTRN>.*?<DTPOSTED>(?P<data>\d{8}).*?<TRNAMT>(?P<valor>[-0-9\.,]+).*?(<MEMO>(?P<memo>.*?))?(<NAME>(?P<name>.*?))?</STMTTRN>", re.IGNORECASE | re.DOTALL)
        for match in padrao.finditer(texto):
            registros.append((match.group("data"), (match.group("memo") or match.group("name") or "").strip(), match.group("valor")))
    else:
        raise ValueError("Formato nao suportado. Use CSV ou OFX.")

    if not registros:
        raise ValueError("Nenhum registro valido foi encontrado.")

    importados = 0
    ignorados = 0
    classificados = 0
    for data_item, descricao, valor in registros:
        data_convertida = parse_date(data_item)
        valor_convertido = parse_decimal(valor)
        if _exists_duplicate_extrato(data_convertida, descricao, valor_convertido, conta.id):
            ignorados += 1
            continue
        extrato = ExtratoImportado(data=data_convertida, descricao=(descricao or "").strip(), valor=valor_convertido, conta_corrente_id=conta.id, conciliado="NAO", id_paroquia=current_user.id_paroquia)
        db.session.add(extrato)
        db.session.flush()
        if _create_imported_launch(extrato):
            classificados += 1
        importados += 1
    db.session.commit()
    return {"importados": importados, "ignorados": ignorados, "classificados": classificados}


def delete_extrato(extrato_id):
    extrato = _find(ExtratoImportado, extrato_id)
    if not extrato:
        raise ValueError("Extrato nao encontrado.")
    if extrato.lancamento_financeiro:
        raise ValueError("Extrato conciliado/classificado nao pode ser excluido sem excluir o lancamento vinculado.")
    db.session.delete(extrato)
    db.session.commit()


def conciliar_extrato(extrato_id, lancamento_id):
    extrato = _find(ExtratoImportado, extrato_id)
    lancamento = _find(LancamentoFinanceiro, lancamento_id)
    if not extrato or not lancamento:
        raise ValueError("Extrato ou lancamento nao encontrado.")
    if extrato.conta_corrente_id != lancamento.conta_corrente_id:
        raise ValueError("Extrato e lancamento precisam estar na mesma conta.")
    extrato.lancamento_financeiro_id = lancamento.id
    extrato.conciliado = "SIM"
    if lancamento.status != "PAGO":
        status_anterior = lancamento.status
        lancamento.status = "PAGO"
        _sync_balance(lancamento, status_anterior=status_anterior)
        if lancamento.duplicata_parcela:
            lancamento.duplicata_parcela.status = "PAGO"
    db.session.commit()
    return extrato


def list_padroes():
    itens = _query(ExtratoPadrao).order_by(ExtratoPadrao.id.desc()).all()
    return [
        {"id": item.id, "descricao_padrao": item.descricao_padrao, "categoria_id": item.categoria_id, "categoria": item.categoria.nome if item.categoria else "", "subcategoria_id": item.subcategoria_id or "", "subcategoria": item.subcategoria.nome if item.subcategoria else "", "centro_custo_id": item.centro_custo_id, "centro_custo": item.centro_custo.nome if item.centro_custo else ""}
        for item in itens
    ]


def save_padrao(padrao_id, descricao_padrao, categoria_id, subcategoria_id, centro_custo_id):
    categoria = _find(CategoriaFinanceira, categoria_id)
    centro = _find(CentroCusto, centro_custo_id)
    sub = _find(SubcategoriaFinanceira, subcategoria_id) if subcategoria_id else None
    if not descricao_padrao or not categoria or not centro:
        raise ValueError("Descricao, categoria e centro de custo sao obrigatorios.")
    if sub and sub.categoria_id != categoria.id:
        raise ValueError("Subcategoria nao pertence a categoria.")
    padrao = _find(ExtratoPadrao, padrao_id) if padrao_id else ExtratoPadrao(id_paroquia=current_user.id_paroquia)
    if not padrao:
        raise ValueError("Padrao nao encontrado.")
    padrao.descricao_padrao = descricao_padrao.strip()
    padrao.categoria_id = categoria.id
    padrao.subcategoria_id = sub.id if sub else None
    padrao.centro_custo_id = centro.id
    db.session.add(padrao)
    db.session.commit()
    return padrao


def delete_padrao(padrao_id):
    padrao = _find(ExtratoPadrao, padrao_id)
    if not padrao:
        raise ValueError("Padrao nao encontrado.")
    db.session.delete(padrao)
    db.session.commit()


def options_context():
    return {
        "contas": list_accounts(),
        "centros": list_centros(),
        "categorias": list_categories(),
        "subcategorias": list_subcategories(),
    }


def save_extrato(extrato_id, data_item, descricao, valor, conta_id):
    conta = _find(ContaCorrente, conta_id)
    if not conta:
        raise ValueError("Conta nao encontrada.")
    extrato = _find(ExtratoImportado, extrato_id) if extrato_id else ExtratoImportado(id_paroquia=current_user.id_paroquia)
    if not extrato:
        raise ValueError("Extrato nao encontrado.")
    if extrato.id and extrato.lancamento_financeiro_id:
        raise ValueError("Nao edite extratos ja conciliados/classificados automaticamente.")
    data_item = parse_date(data_item)
    valor = parse_decimal(valor)
    duplicado = _query(ExtratoImportado).filter_by(data=data_item, descricao=(descricao or "").strip(), valor=valor, conta_corrente_id=conta.id).first()
    if duplicado and duplicado.id != getattr(extrato, "id", None):
        raise ValueError("Este item de extrato ja existe.")
    extrato.data = data_item
    extrato.descricao = (descricao or "").strip()
    extrato.valor = valor
    extrato.conta_corrente_id = conta.id
    if not extrato.id:
        extrato.conciliado = "NAO"
    db.session.add(extrato)
    db.session.commit()
    return extrato
