from flask import session, abort
from functools import wraps
from flask_login import current_user
import hashlib
import hmac
import logging
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from flask import current_app
from sqlalchemy import func, inspect
from werkzeug.utils import secure_filename

from extensions import db
from models import BlocoRifa, ClienteRifa, Equipe, PagamentoRifa, Rifa, RifaCampanha, Vendedor
from rifas.payments import get_pix_gateway
from rifas.pdf_generator import generate_tickets_pdf
from services.public_url_service import build_public_url
from services.whatsapp_service import gerar_link_whatsapp_telefone


logger = logging.getLogger(__name__)

STATUS_DISPONIVEL = "disponivel"
STATUS_RESERVADO = "reservado"
STATUS_PAGO = "pago"
STATUS_CANCELADO = "cancelado"
STATUS_COMPROVANTE = "comprovante"
STATUS_BLOCO = "bloco"
ALLOWED_RECEIPT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".webp"}


class RifaError(Exception):
    pass


class RifaSchemaMissingError(RifaError):
    pass


@dataclass
class PurchaseResult:
    pagamento_id: str
    qr_code_base64: str
    copia_cola_pix: str
    external_id: str
    numeros: list[int]
    valor_total: float
    comprador_nome: str
    quantidade_rifas: int
    status: str
    campanha_titulo: str

    def asdict(self):
        return asdict(self)


def _normalizar_texto(valor: str) -> str:
    return (valor or "").strip()


def _normalize_phone(valor: str) -> str:
    return "".join(ch for ch in (valor or "") if ch.isdigit())


def _utcnow() -> datetime:
    return datetime.utcnow()


def rifas_schema_ready() -> bool:
    inspector = inspect(db.engine)
    tabelas = set(inspector.get_table_names())
    return {
        "clientes",
        "pagamentos",
        "rifas",
        "rifas_campanhas",
        "equipes",
        "vendedores",
        "blocos_rifas",
    }.issubset(tabelas)


def ensure_rifas_schema() -> None:
    if not rifas_schema_ready():
        raise RifaSchemaMissingError(
            "O schema de rifas ainda nao foi criado no banco. Execute 'flask db upgrade' para aplicar as migrations."
        )


def get_active_campaign() -> RifaCampanha | None:
    ensure_rifas_schema()
    return db.session.execute(
        db.select(RifaCampanha).where(RifaCampanha.ativa.is_(True)).order_by(RifaCampanha.created_at.desc())
    ).scalar_one_or_none()


def get_campaign(campanha_id: str) -> RifaCampanha | None:
    ensure_rifas_schema()
    return db.session.get(RifaCampanha, campanha_id)


def list_campaigns() -> list[RifaCampanha]:
    ensure_rifas_schema()
    return db.session.execute(
        db.select(RifaCampanha).order_by(RifaCampanha.ativa.desc(), RifaCampanha.created_at.desc())
    ).scalars().all()


def create_or_update_campaign(*, campanha_id: str | None, titulo: str, descricao: str, data_sorteio, valor_rifa: float, quantidade_total: int, ativa: bool) -> RifaCampanha:
    ensure_rifas_schema()
    titulo = _normalizar_texto(titulo)
    descricao = _normalizar_texto(descricao)

    if not titulo:
        raise RifaError("Titulo da rifa e obrigatorio.")
    if quantidade_total <= 0:
        raise RifaError("Quantidade disponivel deve ser maior que zero.")
    if valor_rifa <= 0:
        raise RifaError("Valor da rifa deve ser maior que zero.")
    if data_sorteio is None:
        raise RifaError("Data do sorteio e obrigatoria.")

    # ✅ RESTAURADO (estava comentado)
    campanha = db.session.get(RifaCampanha, campanha_id) if campanha_id else None

    if campanha is None:
        campanha = RifaCampanha()
        db.session.add(campanha)

    campanha.titulo = titulo
    campanha.descricao = descricao or None
    campanha.data_sorteio = data_sorteio
    valor_rifa = float(str(valor_rifa).replace(",", "."))
    campanha.valor_rifa = Decimal(str(valor_rifa))
    campanha.quantidade_total = quantidade_total
    campanha.ativa = bool(ativa)

    db.session.flush()

    if campanha.ativa:
        db.session.execute(
            db.update(RifaCampanha)
            .where(RifaCampanha.id != campanha.id)
            .values(ativa=False)
        )

    _ensure_inventory(campanha=campanha)

    logger.info("Campanha de rifa salva. campanha_id=%s titulo=%s", campanha.id, campanha.titulo)

    return campanha

def _ensure_inventory(*, campanha: RifaCampanha):
    existentes = db.session.scalar(
        db.select(func.count(Rifa.id)).where(Rifa.campanha_id == campanha.id)
    ) or 0
    faltantes = int(campanha.quantidade_total) - int(existentes)
    if faltantes <= 0:
        return

    ultimo_numero_global = db.session.scalar(db.select(func.max(Rifa.numero))) or 60000
    novos = [
        Rifa(campanha_id=campanha.id, numero=ultimo_numero_global + indice, status=STATUS_DISPONIVEL)
        for indice in range(1, faltantes + 1)
    ]
    db.session.bulk_save_objects(novos)
    db.session.flush()
    logger.info("Estoque da campanha %s inicializado com %s numero(s).", campanha.id, len(novos))


def _validate_purchase_input(nome: str, telefone: str, email: str, quantidade_rifas: int):
    if not nome:
        raise RifaError("Nome e obrigatorio.")

    if not telefone:
        raise RifaError("Telefone e obrigatorio.")

    # 🔒 LIMPA TELEFONE
    telefone_limpo = ''.join(filter(str.isdigit, telefone))

    # 🔒 VALIDA TAMANHO
    if len(telefone_limpo) not in (10, 11):
        raise RifaError("Telefone invalido. Deve ter 10 ou 11 digitos.")

    # 🔒 VALIDA DDD
    ddd = int(telefone_limpo[:2])
    if ddd < 11 or ddd > 99:
        raise RifaError("DDD invalido.")

    # 🔒 VALIDA CELULAR (11 dígitos)
    if len(telefone_limpo) == 11 and telefone_limpo[2] != "9":
        raise RifaError("Celular deve começar com 9.")

    # 🔒 BLOQUEIO DE NUMERO FAKE
    if telefone_limpo == telefone_limpo[0] * len(telefone_limpo):
        raise RifaError("Telefone invalido.")

    # 🔒 EMAIL
    if email:
        if "@" not in email:
           raise RifaError("Email invalido.")
    
    # 🔒 QUANTIDADE
    if quantidade_rifas <= 0:
        raise RifaError("Quantidade de rifas deve ser maior que zero.")

    return telefone_limpo  # 🔥 IMPORTANTE


def _normalizar_codigo_vendedor(codigo: str | None) -> str | None:
    codigo_normalizado = _normalizar_texto(codigo).upper()
    return codigo_normalizado or None


def get_vendedor_by_codigo(codigo: str | None) -> Vendedor | None:
    codigo_normalizado = _normalizar_codigo_vendedor(codigo)
    if not codigo_normalizado:
        return None

    db.session.flush()
    return db.session.execute(
        db.select(Vendedor).where(Vendedor.codigo == codigo_normalizado)
    ).scalar_one_or_none()


def generate_vendor_link(vendedor_codigo: str) -> str:
    codigo_normalizado = _normalizar_codigo_vendedor(vendedor_codigo)
    if not codigo_normalizado:
        raise RifaError("Codigo do vendedor e obrigatorio.")
    return f"/rifas?ref={codigo_normalizado}"


def create_team(*, nome: str, ativa: bool = True) -> Equipe:
    ensure_rifas_schema()
    nome_normalizado = _normalizar_texto(nome)

    if not nome_normalizado:
        raise RifaError("Nome da equipe e obrigatorio.")

    equipe = db.session.execute(
        db.select(Equipe).where(func.upper(Equipe.nome) == nome_normalizado.upper())
    ).scalar_one_or_none()

    if equipe is None:
        equipe = Equipe(nome=nome_normalizado, ativa=ativa)
        db.session.add(equipe)
        db.session.flush()
        return equipe

    equipe.ativa = ativa
    return equipe


def create_vendor(*, nome: str, codigo: str, equipe_id: str, telefone: str = None) -> Vendedor:
    ensure_rifas_schema()
    nome_normalizado = _normalizar_texto(nome)
    codigo_normalizado = _normalizar_codigo_vendedor(codigo)

    if not nome_normalizado:
        raise RifaError("Nome do vendedor e obrigatorio.")
    if not codigo_normalizado:
        raise RifaError("Codigo do vendedor e obrigatorio.")

    equipe = db.session.get(Equipe, equipe_id)
    if equipe is None:
        raise RifaError("Equipe nao encontrada.")
    if not equipe.ativa:
        raise RifaError("Nao e permitido vincular vendedor a uma equipe inativa.")

    vendedor_existente = get_vendedor_by_codigo(codigo_normalizado)
    if vendedor_existente is not None:
        raise RifaError("Ja existe um vendedor com esse codigo.")

    vendedor = Vendedor(nome=nome_normalizado, codigo=codigo_normalizado, equipe_id=equipe.id,telefone=telefone)
    db.session.add(vendedor)
    db.session.flush()
    return vendedor


def _get_campaign_for_block(campanha_id: str | None = None) -> RifaCampanha:
    campanha = get_campaign(campanha_id) if campanha_id else get_active_campaign()
    if campanha is None:
        raise RifaError("Nenhuma campanha de rifa ativa foi cadastrada.")
    return campanha


def create_bloco_rifa(
    *,
    vendedor_codigo: str,
    numero_inicio: int,
    numero_fim: int,
    campanha_id: str | None = None,
) -> BlocoRifa:
    ensure_rifas_schema()
    vendedor_codigo_normalizado = _normalizar_codigo_vendedor(vendedor_codigo)
    db.session.flush()
    vendedor_row = db.session.execute(
        db.select(Vendedor.codigo, Vendedor.equipe_id).where(Vendedor.codigo == vendedor_codigo_normalizado)
    ).one_or_none()

    if vendedor_row is None:
        raise RifaError("Vendedor nao encontrado para o bloco informado.")
    equipe = db.session.get(Equipe, vendedor_row.equipe_id)
    if equipe and not equipe.ativa:
        raise RifaError("Nao e permitido criar bloco para vendedor de equipe inativa.")
    if numero_inicio <= 0 or numero_fim <= 0 or numero_inicio > numero_fim:
        raise RifaError("Intervalo do bloco invalido.")

    campanha = _get_campaign_for_block(campanha_id)
    _ensure_inventory(campanha=campanha)

    bloco_existente = db.session.execute(
        db.select(BlocoRifa).where(
            BlocoRifa.campanha_id == campanha.id,
            BlocoRifa.numero_inicio <= numero_fim,
            BlocoRifa.numero_fim >= numero_inicio,
        )
    ).scalar_one_or_none()
    if bloco_existente is not None:
        raise RifaError("Ja existe um bloco cadastrado para esse intervalo de numeros.")

    # O bloco físico troca o status das rifas para impedir reserva online.
    rifas = db.session.execute(
        db.select(Rifa)
        .where(
            Rifa.campanha_id == campanha.id,
            Rifa.numero >= numero_inicio,
            Rifa.numero <= numero_fim,
        )
        .order_by(Rifa.numero.asc())
    ).scalars().all()

    total_esperado = (numero_fim - numero_inicio) + 1
    if len(rifas) != total_esperado:
        raise RifaError("Existem numeros do intervalo que nao pertencem a campanha ativa.")

    indisponiveis = [rifa.numero for rifa in rifas if rifa.status != STATUS_DISPONIVEL]
    if indisponiveis:
        raise RifaError(
            f"Os numeros {', '.join(str(numero) for numero in indisponiveis)} nao estao disponiveis para bloco."
        )

    bloco = BlocoRifa(
        campanha_id=campanha.id,
        vendedor_codigo=vendedor_row.codigo,
        numero_inicio=numero_inicio,
        numero_fim=numero_fim,
    )
    db.session.add(bloco)

    for rifa in rifas:
        rifa.status = STATUS_BLOCO

    db.session.flush()
    return bloco


def _buscar_ou_criar_cliente(*, nome: str, telefone: str, email: str, endereco: str = None) -> ClienteRifa:
    cliente = db.session.execute(
        db.select(ClienteRifa).where(ClienteRifa.email == email, ClienteRifa.telefone == telefone,ClienteRifa.nome == nome)
    ).scalar_one_or_none()

    if cliente is None:
        cliente = ClienteRifa(
            nome=nome,
            telefone=telefone,
            email=email,
            endereco=endereco
        )
        db.session.add(cliente)
        db.session.flush()
        return cliente

    cliente.nome = nome
    cliente.telefone = telefone
    cliente.endereco = endereco

    return cliente

def get_public_page_data() -> dict:
    ensure_rifas_schema()
    campanha = get_active_campaign()
    disponiveis = 0
    vendidos = 0
    if campanha is not None:
        disponiveis = db.session.scalar(
            db.select(func.count(Rifa.id)).where(Rifa.campanha_id == campanha.id, Rifa.status == STATUS_DISPONIVEL)
        ) or 0
        vendidos = db.session.scalar(
            db.select(func.count(Rifa.id)).where(Rifa.campanha_id == campanha.id, Rifa.status == STATUS_PAGO)
        ) or 0
    return {
        "campanha": campanha,
        "disponiveis": disponiveis,
        "vendidos": vendidos,
    }


def purchase_rifas(*, nome: str, telefone: str, email: str, endereco: str, vendedor: str, quantidade_rifas: int):
    ensure_rifas_schema()
    nome = _normalizar_texto(nome).upper()
    email = _normalizar_texto(email).lower()
    telefone = _validate_purchase_input(nome, telefone, email, quantidade_rifas)
    endereco = _normalizar_texto(endereco).upper()
    #_validate_purchase_input(nome, telefone, email, quantidade_rifas)
    
    
    gateway = get_pix_gateway()

    campanha = db.session.execute(
        db.select(RifaCampanha).where(RifaCampanha.ativa.is_(True)).order_by(RifaCampanha.created_at.desc())
    ).scalar_one_or_none()

    if campanha is None:
        raise RifaError("Nenhuma campanha de rifa ativa foi cadastrada.")

    vendedor_codigo = _normalizar_codigo_vendedor(vendedor)
    vendedor_resolvido = None
    if vendedor_codigo:
        vendedor_obj = get_vendedor_by_codigo(vendedor_codigo)
        if vendedor_obj:
            vendedor = vendedor_obj.nome if vendedor_obj else ""


    equipe_id = None

    if vendedor_codigo:
        db.session.flush()
        vendedor_row = db.session.execute(
            db.select(Vendedor.codigo, Vendedor.equipe_id).where(Vendedor.codigo == vendedor_codigo)
        ).one_or_none()
        if vendedor_row is None:
            raise RifaError("Codigo de vendedor invalido.")
        vendedor_resolvido = vendedor_row.codigo
        equipe_id = vendedor_row.equipe_id
        equipe_ativa = db.session.scalar(
            db.select(Equipe.ativa).where(Equipe.id == vendedor_row.equipe_id)
        )
        if equipe_ativa is False:
            raise RifaError("A equipe vinculada ao vendedor informado esta inativa.")

    valor_unitario = Decimal(str(campanha.valor_rifa))
    valor_total = (valor_unitario * quantidade_rifas).quantize(Decimal("0.00"))


    _ensure_inventory(campanha=campanha)
    #

    cliente = _buscar_ou_criar_cliente(nome=nome, telefone=telefone, email=email, endereco=endereco)

    query = (
        db.select(Rifa)
        .where(Rifa.campanha_id == campanha.id, Rifa.status == STATUS_DISPONIVEL)
        .order_by(Rifa.numero.asc())
        .limit(quantidade_rifas)
    )

    if db.session.bind and db.session.bind.dialect.name != "sqlite":
        query = query.with_for_update(skip_locked=True)

    rifas = db.session.execute(query).scalars().all()

    if len(rifas) < quantidade_rifas:
        raise RifaError("Nao ha quantidade suficiente de rifas disponiveis.")

    charge = gateway.create_charge(
        amount = Decimal(valor_total),
        payer_name=nome,
        payer_email=email,
        description=f"{campanha.titulo} - {quantidade_rifas} rifa(s)",
    )
    txid = ''.join(filter(str.isalnum, (charge.external_id or '')))[:25].upper()
    pagamento = PagamentoRifa(
        campanha_id=campanha.id,
        cliente_id=cliente.id,
        valor_total=valor_total,
        quantidade_rifas=quantidade_rifas,
        status="pendente",
        qr_code_base64=charge.qr_code_base64,
        copia_cola_pix=charge.copia_cola_pix,
        external_id=charge.external_id,
        txid=txid,
        vendedor=vendedor,
        vendedor_codigo=vendedor_resolvido,
        equipe_id=equipe_id,
    )

    db.session.add(pagamento)
    db.session.flush()

    for rifa in rifas:
        rifa.status = STATUS_RESERVADO
        rifa.cliente_id = cliente.id
        rifa.pagamento_id = pagamento.id

    logger.info(
        "Compra iniciada: campanha=%s pagamento=%s txid=%s cliente=%s quantidade=%s numeros=%s",
        campanha.id,
        pagamento.id,
        pagamento.txid,
        cliente.email,
        quantidade_rifas,
        [rifa.numero for rifa in rifas],
    )

    return PurchaseResult(
        pagamento_id=pagamento.id,
        qr_code_base64=pagamento.qr_code_base64 or "",
        copia_cola_pix=pagamento.copia_cola_pix or "",
        external_id=pagamento.external_id or "",
        numeros=[rifa.numero for rifa in rifas],
        valor_total=float(valor_total),
        comprador_nome=cliente.nome,
        quantidade_rifas=quantidade_rifas,
        status=pagamento.status,
        campanha_titulo=campanha.titulo,
    )

def _secure_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left or "", right or "")


def validate_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    expected_secret = current_app.config.get("WEBHOOK_SECRET", "")
    if not expected_secret:
        return True
    digest = hmac.new(expected_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return _secure_compare(digest, signature or "")


def get_payment(payment_id: str) -> PagamentoRifa | None:
    ensure_rifas_schema()
    return db.session.get(PagamentoRifa, payment_id)


def get_payment_by_external_id(external_id: str) -> PagamentoRifa | None:
    ensure_rifas_schema()
    return db.session.execute(
        db.select(PagamentoRifa).where(PagamentoRifa.external_id == external_id)
    ).scalar_one_or_none()

def get_payment_by_txid(txid: str) -> PagamentoRifa | None:
    ensure_rifas_schema()

    return db.session.execute(
        db.select(PagamentoRifa).where(
            func.upper(PagamentoRifa.txid) == txid.upper()
        )
    ).scalar_one_or_none()

def _upload_dir(subdir: str) -> Path:
    path = Path(current_app.root_path) / current_app.config.get("RIFA_UPLOAD_DIR", "static/uploads/rifas") / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def _public_static_path(subdir: str, filename: str) -> str:
    base = current_app.config.get("RIFA_UPLOAD_DIR", "static/uploads/rifas").replace("\\", "/").strip("/")
    return f"/{base}/{subdir}/{filename}" if subdir else f"/{base}/{filename}"


def _save_receipt_cloudinary(*, arquivo):
    import cloudinary
    import cloudinary.uploader

    try:
        if not arquivo:
            return None, None

        cloudinary_url = (
            current_app.config.get("CLOUDINARY_URL")
            or os.environ.get("CLOUDINARY_URL")
        )

        if cloudinary_url:
            cloudinary.config(cloudinary_url=cloudinary_url)
        else:
            cloudinary.config(
                cloud_name=current_app.config.get("CLOUDINARY_CLOUD_NAME"),
                api_key=current_app.config.get("CLOUDINARY_API_KEY"),
                api_secret=current_app.config.get("CLOUDINARY_API_SECRET"),
            )

        filename = secure_filename(arquivo.filename)

        if not filename:
            return None, None

        ext = Path(filename).suffix.lower()

        if ext not in ALLOWED_RECEIPT_EXTENSIONS:
            raise RifaError("Formato não permitido")

        # 🔥 upload sempre executa
        upload = cloudinary.uploader.upload(
            arquivo.stream,
            folder="rifas/comprovantes",
            resource_type="auto"
        )

        url = upload.get("secure_url")
        extensao = upload.get("format")

        return url, extensao

    except Exception as e:
        print("ERRO CLOUDINARY:", str(e))
        return None, None
    
def save_receipt(*, pagamento_id: str, arquivo) -> PagamentoRifa:
    ensure_rifas_schema()

    pagamento = db.session.get(PagamentoRifa, pagamento_id)
    if pagamento is None:
        raise RifaError("Pagamento nao encontrado.")

    if arquivo is None or not getattr(arquivo, "filename", ""):
        raise RifaError("Selecione um comprovante para enviar.")

    filename = secure_filename(arquivo.filename)
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_RECEIPT_EXTENSIONS:
        raise RifaError("Formato de comprovante nao permitido.")

    try:
        url, extensao = _save_receipt_cloudinary(arquivo=arquivo)

        if not url:
            raise RifaError("Erro ao enviar comprovante")

        pagamento.comprovante_path = url
        pagamento.comprovante_ext = extensao
        pagamento.comprovante_nome = filename
        pagamento.comprovante_enviado_em = _utcnow()
        pagamento.status = STATUS_COMPROVANTE

        db.session.commit()

        logger.info(
            "Comprovante enviado pagamento=%s url=%s",
            pagamento.id,
            pagamento.comprovante_path
        )

        return pagamento

    except Exception as e:
        db.session.rollback()
        raise RifaError(f"Erro ao enviar comprovante: {str(e)}")
    
def confirm_payment(*, external_id: str | None = None, pagamento_id: str | None = None, observacoes_admin: str | None = None) -> PagamentoRifa:
    # 🔍 1. Buscar pagamento
    pagamento = None

    if pagamento_id:
        pagamento = db.session.get(PagamentoRifa, pagamento_id)

    if pagamento is None and external_id:
        pagamento = get_payment_by_external_id(external_id)

    if pagamento is None:
        raise RifaError("Pagamento nao encontrado.")

    # 🔁 2. Idempotência (se já está pago, retorna)
    if pagamento.status in [STATUS_PAGO, STATUS_CANCELADO]:
        return pagamento

    # 🔒 3. Verifica campanha
    campanha = pagamento.campanha
    if campanha is None:
        raise RifaError("Campanha nao encontrada para este pagamento.")

    # ⏰ 4. Verifica expiração
    reserva_minutos = int(current_app.config["RIFA_RESERVA_MINUTOS"])
    limite = pagamento.created_at + timedelta(minutes=reserva_minutos)
    expirado = datetime.utcnow() > limite

    # 🔄 5. Se expirou → precisa reatribuir rifas
    if expirado:
        logger.warning(f"Pagamento {pagamento.id} confirmado apos expiracao. Reatribuindo rifas...")

        # 🔍 Busca novas rifas disponíveis
        query = (
            db.select(Rifa)
            .where(
                Rifa.campanha_id == campanha.id,
                Rifa.status == STATUS_DISPONIVEL
            )
            .order_by(Rifa.numero.asc())
            .limit(pagamento.quantidade_rifas)
        )

        if db.session.bind and db.session.bind.dialect.name != "sqlite":
            query = query.with_for_update(skip_locked=True)

        novas_rifas = db.session.execute(query).scalars().all()

        if len(novas_rifas) < pagamento.quantidade_rifas:
            raise RifaError("Pagamento recebido apos expiracao, mas nao ha rifas disponiveis.")

        # 🔄 Limpa rifas antigas (se ainda existirem)
        for rifa in pagamento.rifas:
            rifa.status = STATUS_DISPONIVEL
            rifa.pagamento_id = None
            rifa.cliente_id = None

        # 🔗 Vincula novas rifas
        for rifa in novas_rifas:
            rifa.status = STATUS_PAGO
            rifa.pagamento_id = pagamento.id
            rifa.cliente_id = pagamento.cliente_id

        pagamento.rifas = novas_rifas

    else:
        # ✅ 6. Fluxo normal (não expirado)
        for rifa in pagamento.rifas:
            rifa.status = STATUS_PAGO

    # 💾 7. Atualiza pagamento
    pagamento.status = STATUS_PAGO
    pagamento.pago_em = datetime.utcnow()
    pagamento.observacoes_admin = observacoes_admin

    # 🧾 8. Gerar PDF (opcional)
    try:
        from rifas.pdf_generator import generate_tickets_pdf

        generate_tickets_pdf(
            pagamento=pagamento,
            rifas=sorted(pagamento.rifas, key=lambda r: r.numero),
            cliente=pagamento.cliente,
        )
    except Exception as e:
        logger.error(f"Erro ao gerar PDF pagamento {pagamento.id}: {str(e)}")

    logger.info(f"Pagamento confirmado com sucesso: {pagamento.id}")

    return pagamento

def process_webhook(payload: dict, raw_body: bytes, signature: str | None) -> PagamentoRifa:
    if not validate_webhook_signature(raw_body, signature):
        raise RifaError("Assinatura do webhook invalida.")

    gateway = get_pix_gateway()

    identifier, status = gateway.parse_webhook(payload)

    if not identifier:
        raise RifaError("Webhook sem identificador.")

    pagamento = get_payment_by_txid(identifier)

    if not pagamento:
        pagamento = get_payment_by_external_id(identifier)

    if not pagamento:
        raise RifaError(f"Pagamento nao encontrado: {identifier}")

    if pagamento.status in [STATUS_PAGO, STATUS_CANCELADO]:
        return pagamento

    if status.lower() in ["pago", "paid", "approved"]:
        return confirm_payment(pagamento_id=pagamento.id)

    raise RifaError("Webhook sem confirmacao de pagamento.")

def payment_summary(pagamento: PagamentoRifa) -> dict:
    rifas = sorted((rifa.numero for rifa in pagamento.rifas), key=int)
    return {
        "id": pagamento.id,
        "status": pagamento.status,
        "valor_total": float(pagamento.valor_total),
        "quantidade_rifas": pagamento.quantidade_rifas,
        "qr_code_base64": pagamento.qr_code_base64,
        "copia_cola_pix": pagamento.copia_cola_pix,
        "external_id": pagamento.external_id,
        "created_at": pagamento.created_at.isoformat() if pagamento.created_at else None,
        "pago_em": pagamento.pago_em.isoformat() if pagamento.pago_em else None,
        "cliente": {
            "id": pagamento.cliente.id,
            "nome": pagamento.cliente.nome,
            "telefone": pagamento.cliente.telefone,
        } if pagamento.cliente else None,
        "campanha": {
            "id": pagamento.campanha.id,
            "titulo": pagamento.campanha.titulo,
            "data_sorteio": pagamento.campanha.data_sorteio.isoformat() if pagamento.campanha and pagamento.campanha.data_sorteio else None,
            "valor_rifa": float(pagamento.campanha.valor_rifa),
        } if pagamento.campanha else None,
        "vendedor": pagamento.vendedor,
        "vendedor_codigo": pagamento.vendedor_codigo,
        "equipe": {
            "id": pagamento.equipe.id,
            "nome": pagamento.equipe.nome,
        } if pagamento.equipe else None,
        "rifas": rifas,
        "pdf_path": pagamento.pdf_path,
        "comprovante_path": pagamento.comprovante_path,
        "comprovante_nome": pagamento.comprovante_nome,
    }


def payment_pdf_public_url(pagamento: PagamentoRifa) -> str:
    return build_public_url("rifas_public.pagamento_pdf_publico", payment_id=pagamento.id)


def payment_whatsapp_link(pagamento: PagamentoRifa) -> str | None:
    rifas = sorted((rifa.numero for rifa in pagamento.rifas), key=int)
    numeros = ", ".join(f"{numero:04d}" for numero in rifas)

    campanha = pagamento.campanha.titulo if pagamento.campanha else "Rifa"

    data_sorteio = (
        pagamento.campanha.data_sorteio.strftime("%d/%m/%Y")
        if pagamento.campanha and pagamento.campanha.data_sorteio
        else ""
    )

    valor_formatado = format(float(pagamento.valor_total), ".2f").replace(".", ",")

    mensagem = (
        f"🎉 *Pagamento confirmado com sucesso!*\n\n"

        f"Olá *{pagamento.cliente.nome}*, tudo bem? 😊\n\n"

        f"Sua participação na *{campanha}* foi confirmada! 🙌\n\n"

        f"🎟️ *Seus números:* {numeros}\n"
        f"💰 *Valor pago:* R$ {valor_formatado}\n"
        f"📅 *Sorteio final:* {data_sorteio}\n\n"

        f"---\n\n"

        f"🔥 *Confira os prêmios incríveis:*\n\n"

        f"📅 03/05 → 💵 R$ 3.000,00\n"
        f"📅 07/06 → 📱 iPhone 16 Pro Max\n"
        f"📅 08/08 → 💵 R$ 3.000,00\n"
        f"📅 13/09 → 💵 R$ 3.000,00\n\n"

        f"🚗 *Sorteio Final (12/10):*\n"
        f"🎁 Fiat Mobi\n\n"

        f"• 01 ano de combustível\n"
        f"• 01 ano de seguro\n"
        f"• 01 ano de lavagem\n\n"

        f"---\n\n"

        f"🙏 Muito obrigado por participar e boa sorte! 🍀\n"
        f"Qualquer dúvida, estamos à disposição."
    )

    return gerar_link_whatsapp_telefone(pagamento.cliente.telefone, mensagem)

def payment_detail_data(pagamento_id: str) -> dict:
    pagamento = get_payment(pagamento_id)
    if pagamento is None:
        raise RifaError("Pagamento nao encontrado.")
    return {
        "pagamento": pagamento,
        "numeros": sorted(pagamento.rifas, key=lambda item: item.numero),
        "whatsapp_link": payment_whatsapp_link(pagamento) if pagamento.status == STATUS_PAGO else None,
        "pdf_public_url": payment_pdf_public_url(pagamento) if pagamento.pdf_path else None,
    }


def admin_dashboard_data() -> dict:
    ensure_rifas_schema()
    pagamentos = db.session.execute(
        db.select(PagamentoRifa).order_by(PagamentoRifa.created_at.desc())
    ).scalars().all()
    clientes = db.session.execute(
        db.select(ClienteRifa).order_by(ClienteRifa.created_at.desc())
    ).scalars().all()
    rifas = db.session.execute(
        db.select(Rifa).order_by(Rifa.campanha_id.asc(), Rifa.numero.asc())
    ).scalars().all()
    campanhas = list_campaigns()
    campanha_ativa = next((item for item in campanhas if item.ativa), None)

    total_pago = sum(float(item.valor_total) for item in pagamentos if item.status == STATUS_PAGO)
    disponiveis = sum(1 for item in rifas if item.status == STATUS_DISPONIVEL)
    reservadas = sum(1 for item in rifas if item.status == STATUS_RESERVADO)
    pagas = sum(1 for item in rifas if item.status == STATUS_PAGO)

    ranking_map = {}
    for pagamento in pagamentos:
        if pagamento.status != STATUS_PAGO or not pagamento.cliente:
            continue
        chave = pagamento.cliente.id
        if chave not in ranking_map:
            ranking_map[chave] = {
                "cliente": pagamento.cliente,
                "quantidade": 0,
                "valor_total": 0.0,
            }
        ranking_map[chave]["quantidade"] += pagamento.quantidade_rifas
        ranking_map[chave]["valor_total"] += float(pagamento.valor_total)

    ranking_compradores = sorted(
        ranking_map.values(),
        key=lambda item: (-item["quantidade"], -item["valor_total"], item["cliente"].nome),
    )[:10]

    return {
        "pagamentos": pagamentos,
        "clientes": clientes,
        "rifas": rifas,
        "campanhas": campanhas,
        "campanha_ativa": campanha_ativa,
        "ranking_compradores": ranking_compradores,
        "stats": {
            "total_pago": total_pago,
            "disponiveis": disponiveis,
            "reservadas": reservadas,
            "pagas": pagas,
            "clientes": len(clientes),
            "pagamentos": len(pagamentos),
        },
    }

def formatar_telefone(tel):
    tel = ''.join(filter(str.isalnum, tel or ''))
    tel = ''.join(filter(str.isdigit, tel))

    if len(tel) == 11:
        return f"({tel[:2]}) {tel[2:7]}-{tel[7:]}"
    elif len(tel) == 10:
        return f"({tel[:2]}) {tel[2:6]}-{tel[6:]}"
    return tel

def cancelar_pagamento(*, pagamento_id: str) -> PagamentoRifa:
    pagamento = db.session.get(PagamentoRifa, pagamento_id)

    if pagamento is None:
        raise RifaError("Pagamento não encontrado.")

    # 🔥 só bloqueia se já estiver cancelado
    if pagamento.status == STATUS_CANCELADO:
        raise RifaError("Pagamento já está cancelado.")

    # 🔥 libera rifas (se existirem)
    for rifa in pagamento.rifas:
        rifa.status = STATUS_DISPONIVEL
        rifa.pagamento_id = None
        rifa.cliente_id = None

    # 🔥 atualiza pagamento
    pagamento.status = STATUS_CANCELADO
    pagamento.pago_em = None
    pagamento.pdf_path = None

    try:
        pagamento.cancelado_em = _utcnow()
    except:
        pass

    logger.info("Pagamento cancelado manualmente: %s", pagamento.id)

    db.session.commit()
    return pagamento

def cancelar_pagamentos_expirados():

    agora = datetime.utcnow()
    reserva_minutos = int(current_app.config.get("RIFA_RESERVA_MINUTOS", 60))
    limite = agora - timedelta(minutes=reserva_minutos)

    pagamentos = db.session.execute(
        db.select(PagamentoRifa).where(
            PagamentoRifa.status == "pendente",
            PagamentoRifa.created_at < limite
        )
    ).scalars().all()

    for p in pagamentos:
        logger.info(
            "RIFA EXPIRADA | pagamento=%s | cliente=%s | qtd=%s | criado_em=%s",
            p.id,
            p.cliente_id,
             p.quantidade_rifas,
             p.created_at
        )

        # 🔥 liberar rifas
        for rifa in p.rifas:
            rifa.status = "disponivel"
            rifa.pagamento_id = None
             # 🔥 LIMPA O CLIENTE TAMBÉM
            rifa.cliente_id = None

        p.status = "cancelado"

    #if pagamentos:
     #   db.session.commit()


def limpeza_completa_rifas():
    ensure_rifas_schema()

    from sqlalchemy import text
    from extensions import db

    # 🔥 1. LIBERAR RIFAS DE PAGAMENTOS CANCELADOS
    db.session.execute(text("""
        UPDATE rifas
        SET status = 'disponivel',
            cliente_id = NULL,
            pagamento_id = NULL
        WHERE pagamento_id IN (
            SELECT id FROM pagamentos WHERE status = 'cancelado'
        )
    """))

    # 🔥 2. DELETAR PAGAMENTOS CANCELADOS
    result_pag = db.session.execute(text("""
        DELETE FROM pagamentos
        WHERE status = 'cancelado'
        RETURNING id
    """))

    pagamentos_deletados = result_pag.fetchall()

    # 🔥 3. DELETAR CLIENTES SEM PAGAMENTOS
    result_cli = db.session.execute(text("""
        DELETE FROM clientes c
        WHERE NOT EXISTS (
            SELECT 1
            FROM pagamentos p
            WHERE p.cliente_id = c.id
        )
        RETURNING c.id
    """))

    clientes_deletados = result_cli.fetchall()

    return {
        "pagamentos": len(pagamentos_deletados),
        "clientes": len(clientes_deletados)
    }

def acesso_rifas_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and current_user.is_admin():
            session["acesso_rifas"] = True
            session["perfil"] = "admin"
            return f(*args, **kwargs)

        if not session.get("acesso_rifas"):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def update_team(equipe_id: str, nome: str, ativa: bool):
    ensure_rifas_schema()
    equipe = db.session.get(Equipe, equipe_id)
    if not equipe:
        raise RifaError("Equipe nao encontrada.")

    nome_normalizado = _normalizar_texto(nome)
    if not nome_normalizado:
        raise RifaError("Nome da equipe e obrigatorio.")

    equipe_existente = db.session.execute(
        db.select(Equipe).where(
            func.upper(Equipe.nome) == nome_normalizado.upper(),
            Equipe.id != equipe.id,
        )
    ).scalar_one_or_none()
    if equipe_existente is not None:
        raise RifaError("Ja existe outra equipe com esse nome.")

    equipe.nome = nome_normalizado
    equipe.ativa = ativa
    return equipe


def delete_team(equipe_id: str):
    ensure_rifas_schema()
    equipe = db.session.get(Equipe, equipe_id)
    if not equipe:
        raise RifaError("Equipe nao encontrada.")

    possui_vendedores = db.session.scalar(
        db.select(func.count(Vendedor.id)).where(Vendedor.equipe_id == equipe.id)
    ) or 0
    if possui_vendedores:
        raise RifaError("Nao e permitido excluir equipe com vendedores vinculados.")

    pagamentos = db.session.execute(
        db.select(PagamentoRifa).where(PagamentoRifa.equipe_id == equipe.id)
    ).scalars().all()
    for pagamento in pagamentos:
        pagamento.equipe_id = None

    db.session.delete(equipe)


def update_vendor(vendedor_id: str, nome: str, codigo: str, equipe_id: str, telefone: str = None):
    ensure_rifas_schema()
    vendedor = db.session.get(Vendedor, vendedor_id)
    if not vendedor:
        raise RifaError("Vendedor nao encontrado.")

    nome_normalizado = _normalizar_texto(nome)
    codigo_normalizado = _normalizar_codigo_vendedor(codigo)

    if not nome_normalizado:
        raise RifaError("Nome do vendedor e obrigatorio.")
    if not codigo_normalizado:
        raise RifaError("Codigo do vendedor e obrigatorio.")

    equipe = db.session.get(Equipe, equipe_id)
    if not equipe:
        raise RifaError("Equipe nao encontrada.")
    if not equipe.ativa:
        raise RifaError("Nao e permitido vincular vendedor a uma equipe inativa.")

    vendedor_existente = db.session.execute(
        db.select(Vendedor).where(
            func.upper(Vendedor.codigo) == codigo_normalizado.upper(),
            Vendedor.id != vendedor.id,
        )
    ).scalar_one_or_none()
    if vendedor_existente is not None:
        raise RifaError("Ja existe outro vendedor com esse codigo.")

    codigo_anterior = vendedor.codigo
    if codigo_anterior != codigo_normalizado:
        total_pagamentos = db.session.scalar(
            db.select(func.count(PagamentoRifa.id)).where(PagamentoRifa.vendedor_codigo == codigo_anterior)
        ) or 0
        total_blocos = db.session.scalar(
            db.select(func.count(BlocoRifa.id)).where(BlocoRifa.vendedor_codigo == codigo_anterior)
        ) or 0
        if total_pagamentos or total_blocos:
            raise RifaError(
                "Nao e permitido alterar o codigo de vendedor que ja possui pagamentos ou blocos vinculados."
            )

    vendedor.nome = nome_normalizado
    vendedor.codigo = codigo_normalizado
    vendedor.equipe_id = equipe_id
    if telefone is not None:
        telefone_limpo = _normalize_phone(telefone)
        if telefone_limpo:
            vendedor.telefone = telefone_limpo

    pagamentos_equipe = db.session.execute(
        db.select(PagamentoRifa).where(PagamentoRifa.vendedor_codigo == vendedor.codigo)
    ).scalars().all()
    for pagamento in pagamentos_equipe:
        pagamento.equipe_id = equipe.id

    return vendedor


def delete_vendor(vendedor_id: str):
    ensure_rifas_schema()
    vendedor = db.session.get(Vendedor, vendedor_id)
    if not vendedor:
        raise RifaError("Vendedor nao encontrado.")

    possui_blocos = db.session.scalar(
        db.select(func.count(BlocoRifa.id)).where(BlocoRifa.vendedor_codigo == vendedor.codigo)
    ) or 0
    if possui_blocos:
        raise RifaError("Nao e permitido excluir vendedor com blocos cadastrados.")

    pagamentos = db.session.execute(
        db.select(PagamentoRifa).where(PagamentoRifa.vendedor_codigo == vendedor.codigo)
    ).scalars().all()
    for pagamento in pagamentos:
        if not pagamento.vendedor:
            pagamento.vendedor = vendedor.nome
        pagamento.vendedor_codigo = None

    db.session.delete(vendedor)

def gerar_mensagem_vendedor(codigo):
    link = f"https://sgme.onrender.com/acao_entre_fieis?ref={codigo}"

    mensagem = f"""Oi 😊 tudo bem?

Estou participando de uma ação entre fiéis da igreja 🙏
Se você puder ajudar, pode adquirir sua rifa direto por aqui:

👉 {link}

Os números são gerados automaticamente pelo sistema, de forma rápida e segura 👍

Você preenche seus dados no próprio link, o sistema já gera o QR Code do Pix, você faz o pagamento e pode enviar o comprovante ali mesmo na tela.

📌 Importante:
Comprando pelo link, não precisa canhoto nem bloco — já fica tudo registrado automaticamente.

Qualquer ajuda já faz muita diferença 🙌
Deus abençoe!
"""
    return mensagem

import urllib.parse

def gerar_link_whatsapp(codigo):
    mensagem = gerar_mensagem_vendedor(codigo)
    mensagem_encoded = urllib.parse.quote(mensagem)

    return f"https://wa.me/?text={mensagem_encoded}"

from datetime import datetime, timedelta
from urllib.parse import quote

def lembrar_comprovante():
    agora = datetime.utcnow()
    limite = agora - timedelta(minutes=30)

    pagamentos = db.session.execute(
        db.select(PagamentoRifa).where(
            PagamentoRifa.status == "pendente",
            PagamentoRifa.created_at < limite
        )
    ).scalars().all()

    for p in pagamentos:
        if not p.cliente or not p.cliente.telefone:
            continue

        link = build_public_url("rifas_public.pagamento_detalhe", payment_id=p.id)

        mensagem = f"""Olá {p.cliente.nome} 😊

Você iniciou a compra da rifa, mas ainda não enviou o comprovante.

👉 Envie aqui:
{link}

⏰ Sua reserva pode expirar!

Deus abençoe 🙌
"""

        telefone = ''.join(filter(str.isdigit, p.cliente.telefone))
        whatsapp_link = f"https://wa.me/55{telefone}?text={quote(mensagem)}"

        print("LEMBRETE:", whatsapp_link)

def gerar_url_cloudinary(public_id, extensao):
    base = "https://res.cloudinary.com/dwlsuncxm"

    if extensao == "pdf":
        return f"{base}/raw/upload/{public_id}.pdf"
    else:
        return f"{base}/image/upload/{public_id}.{extensao}"

def gerar_novas_rifas_pagamento(pagamento):
    from rifas.models import Rifa

    # 🔥 1. LIBERAR RIFAS ANTIGAS
    for rifa in pagamento.rifas:
        rifa.status = "disponivel"
        rifa.pagamento_id = None
        rifa.cliente_id = None

    # 🔥 2. GERAR NOVAS RIFAS AUTOMÁTICAS
    novas = db.session.execute(
        db.select(Rifa).where(
            Rifa.campanha_id == pagamento.campanha_id,
            Rifa.status == "disponivel"
        ).limit(pagamento.quantidade_rifas)
    ).scalars().all()

    if len(novas) < pagamento.quantidade_rifas:
        raise Exception("Não há rifas suficientes disponíveis")

    for rifa in novas:
        rifa.status = "reservado"
        rifa.pagamento_id = pagamento.id
        rifa.cliente_id = pagamento.cliente_id
