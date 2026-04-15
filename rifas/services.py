import hashlib
import hmac
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from flask import current_app
from sqlalchemy import func, inspect
from werkzeug.utils import secure_filename

from extensions import db
from models import ClienteRifa, PagamentoRifa, Rifa, RifaCampanha
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
    return {"clientes", "pagamentos", "rifas", "rifas_campanhas"}.issubset(tabelas)


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

    ultimo_numero_global = db.session.scalar(db.select(func.max(Rifa.numero))) or 0
    novos = [
        Rifa(campanha_id=campanha.id, numero=ultimo_numero_global + indice, status=STATUS_DISPONIVEL)
        for indice in range(1, faltantes + 1)
    ]
    db.session.bulk_save_objects(novos)
    db.session.flush()
    logger.info("Estoque da campanha %s inicializado com %s numero(s).", campanha.id, len(novos))


def _release_expired_reservations():
    reserva_minutos = int(current_app.config["RIFA_RESERVA_MINUTOS"])
    limite = _utcnow() - timedelta(minutes=reserva_minutos)
    expirados = db.session.execute(
        db.select(PagamentoRifa).where(
            PagamentoRifa.status == "pendente",
            PagamentoRifa.created_at < limite,
        )
    ).scalars().all()
    for pagamento in expirados:
        for rifa in pagamento.rifas:
            rifa.status = STATUS_DISPONIVEL
            rifa.pagamento_id = None
            rifa.cliente_id = None
        pagamento.status = STATUS_CANCELADO
    if expirados:
        logger.info("Reservas expiradas liberadas: %s", len(expirados))
        db.session.flush()


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


def purchase_rifas(*, nome: str, telefone: str, email: str, endereco: str,vendedor: str, quantidade_rifas: int):
    ensure_rifas_schema()
    nome = _normalizar_texto(nome)
    email = _normalizar_texto(email).lower()
    telefone = _validate_purchase_input(nome, telefone, email, quantidade_rifas)
    endereco = _normalizar_texto(endereco).lower()
    #_validate_purchase_input(nome, telefone, email, quantidade_rifas)
    
    
    gateway = get_pix_gateway()

    campanha = db.session.execute(
        db.select(RifaCampanha).where(RifaCampanha.ativa.is_(True)).order_by(RifaCampanha.created_at.desc())
    ).scalar_one_or_none()

    if campanha is None:
        raise RifaError("Nenhuma campanha de rifa ativa foi cadastrada.")

    valor_unitario = Decimal(str(campanha.valor_rifa))
    valor_total = (valor_unitario * quantidade_rifas).quantize(Decimal("0.00"))


    _ensure_inventory(campanha=campanha)
    _release_expired_reservations()

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

    pagamento = PagamentoRifa(
        campanha_id=campanha.id,
        cliente_id=cliente.id,
        valor_total=valor_total,
        quantidade_rifas=quantidade_rifas,
        status="pendente",
        qr_code_base64=charge.qr_code_base64,
        copia_cola_pix=charge.copia_cola_pix,
        external_id=charge.external_id,
        vendedor=vendedor,  # ✅ NOVO
    )

    db.session.add(pagamento)
    db.session.flush()

    for rifa in rifas:
        rifa.status = STATUS_RESERVADO
        rifa.cliente_id = cliente.id
        rifa.pagamento_id = pagamento.id

    logger.info(
        "Compra iniciada: campanha=%s pagamento=%s cliente=%s quantidade=%s numeros=%s",
        campanha.id,
        pagamento.id,
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


def _upload_dir(subdir: str) -> Path:
    path = Path(current_app.root_path) / current_app.config.get("RIFA_UPLOAD_DIR", "static/uploads/rifas") / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def _public_static_path(subdir: str, filename: str) -> str:
    base = current_app.config.get("RIFA_UPLOAD_DIR", "static/uploads/rifas").replace("\\", "/").strip("/")
    return f"/{base}/{subdir}/{filename}" if subdir else f"/{base}/{filename}"


import cloudinary.uploader

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

    # 🔥 ENVIA PARA CLOUDINARY
    upload = cloudinary.uploader.upload(
        arquivo.stream,
        folder="rifas/comprovantes",
        public_id=f"{pagamento.id}_{uuid.uuid4().hex[:6]}",
        resource_type="auto"
    )
    # 🔥 SALVA URL (não caminho local)
    pagamento.comprovante_path = upload["secure_url"]
    pagamento.comprovante_nome = filename
    pagamento.comprovante_enviado_em = _utcnow()

    # 🔥 STATUS
    pagamento.status = STATUS_COMPROVANTE

    db.session.commit()

    logger.info(
        "Comprovante enviado (Cloudinary) pagamento=%s url=%s",
        pagamento.id,
        pagamento.comprovante_path
    )

    return pagamento

def confirm_payment(*, external_id: str | None = None, pagamento_id: str | None = None, observacoes_admin: str | None = None) -> PagamentoRifa:
    pagamento = None

    if pagamento_id:
        pagamento = db.session.get(PagamentoRifa, pagamento_id)

    if pagamento is None and external_id:
        pagamento = get_payment_by_external_id(external_id)

    if pagamento is None:
        raise RifaError("Pagamento nao encontrado.")

    if pagamento.status == STATUS_PAGO:
        return pagamento

    if pagamento.status == STATUS_CANCELADO:
        raise RifaError("Este pagamento já foi cancelado e não pode ser confirmado.")

        # buscar novas rifas disponíveis
        rifas = db.session.execute(
            db.select(Rifa)
            .where(
                Rifa.campanha_id == campanha.id,
                Rifa.status == STATUS_DISPONIVEL
            )
            .order_by(Rifa.numero.asc())
            .limit(pagamento.quantidade_rifas)
        ).scalars().all()

        if len(rifas) < pagamento.quantidade_rifas:
            raise RifaError("Pagamento recebido após expiração, mas não há rifas disponíveis.")

        # vincular novas rifas
        for rifa in rifas:
            rifa.status = STATUS_PAGO
            rifa.cliente_id = pagamento.cliente_id
            rifa.pagamento_id = pagamento.id

        pagamento.rifas = rifas

        pagamento.observacoes_admin = "Pagamento recebido após expiração"

    else:
        # fluxo normal
        for rifa in pagamento.rifas:
            rifa.status = STATUS_PAGO
            rifa.cliente_id = pagamento.cliente_id
            rifa.pagamento_id = pagamento.id

    # ✅ FINALIZA PAGAMENTO
    pagamento.status = STATUS_PAGO
    pagamento.pago_em = _utcnow()

    if observacoes_admin:
        pagamento.observacoes_admin = observacoes_admin

    # 🔥 GERA PDF COM NOVAS RIFAS
    pdf_path = generate_tickets_pdf(
        pagamento=pagamento,
        rifas=sorted(pagamento.rifas, key=lambda item: item.numero),
        cliente=pagamento.cliente,
    )

    pagamento.pdf_path = pdf_path

    logger.info("Pagamento confirmado: pagamento=%s external_id=%s", pagamento.id, pagamento.external_id)

    return pagamento

def process_webhook(payload: dict, raw_body: bytes, signature: str | None) -> PagamentoRifa:
    if not validate_webhook_signature(raw_body, signature):
        raise RifaError("Assinatura do webhook invalida.")
    gateway = get_pix_gateway()
    external_id, status = gateway.parse_webhook(payload)
    if status not in {"approved", "paid", "pago", "payment.updated"} and payload.get("tipo") != "pago":
        raise RifaError("Webhook recebido sem confirmacao de pagamento.")
    pagamento_id = payload.get("pagamento_id")
    return confirm_payment(external_id=external_id, pagamento_id=pagamento_id)


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
            "email": pagamento.cliente.email,
        } if pagamento.cliente else None,
        "campanha": {
            "id": pagamento.campanha.id,
            "titulo": pagamento.campanha.titulo,
            "data_sorteio": pagamento.campanha.data_sorteio.isoformat() if pagamento.campanha and pagamento.campanha.data_sorteio else None,
            "valor_rifa": float(pagamento.campanha.valor_rifa),
        } if pagamento.campanha else None,
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
    data_sorteio = pagamento.campanha.data_sorteio.strftime("%d/%m/%Y") if pagamento.campanha and pagamento.campanha.data_sorteio else ""
    link_pdf = payment_pdf_public_url(pagamento) if pagamento.pdf_path else ""
    mensagem = (
        f"Ola {pagamento.cliente.nome}, seu pagamento da {campanha} foi confirmado.\n\n"
        f"Numeros adquiridos: {numeros}\n"
        f"Sorteio: {data_sorteio}\n"
        f"Valor pago: R$ {float(pagamento.valor_total):.2f}\n"
    )
    
    #if link_pdf:
        #mensagem += f"\nBaixar canhotos: {link_pdf}\n"

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

    if pagamento.status != STATUS_PAGO:
        raise RifaError("Só é possível cancelar pagamentos já pagos.")

    # 🔥 Volta as rifas para disponível
    for rifa in pagamento.rifas:
        rifa.status = STATUS_DISPONIVEL
        rifa.pagamento_id = None
        rifa.cliente_id = None

    # 🔥 Atualiza pagamento
    pagamento.status = STATUS_CANCELADO
    pagamento.pago_em = None
    pagamento.pdf_path = None

    logger.info("Pagamento cancelado manualmente: %s", pagamento.id)

    return pagamento

from datetime import datetime, timedelta
from extensions import db
from models import PagamentoRifa

def cancelar_pagamentos_expirados():
    from datetime import datetime, timedelta
    from extensions import db
    from models import PagamentoRifa, Rifa

    agora = datetime.utcnow()
    limite = agora - timedelta(minutes=60)

    pagamentos = db.session.execute(
        db.select(PagamentoRifa).where(
            PagamentoRifa.status == "pendente",
            PagamentoRifa.created_at < limite
        )
    ).scalars().all()

    for p in pagamentos:
        # 🔥 liberar rifas
        for rifa in p.rifas:
            rifa.status = "disponivel"
            rifa.pagamento_id = None
             # 🔥 LIMPA O CLIENTE TAMBÉM
            rifa.cliente_id = None

        p.status = "cancelado"

    if pagamentos:
        db.session.commit()

    import cloudinary

    cloudinary.config(
        cloud_name="Raiz",
        api_key="S949366984135176",
        api_secret="SEFcYC63EUHgdT_aprgI8kpf7Wuc"
    )



