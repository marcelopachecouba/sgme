import hashlib
import hmac
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from flask import current_app
from sqlalchemy import func, inspect

from extensions import db
from models import ClienteRifa, PagamentoRifa, Rifa
from rifas.payments import get_pix_gateway
from rifas.pdf_generator import generate_tickets_pdf


logger = logging.getLogger(__name__)

STATUS_DISPONIVEL = "disponivel"
STATUS_RESERVADO = "reservado"
STATUS_PAGO = "pago"
STATUS_CANCELADO = "cancelado"


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

    def asdict(self):
        return asdict(self)


def _normalizar_texto(valor: str) -> str:
    return (valor or "").strip()


def _normalize_phone(valor: str) -> str:
    return "".join(ch for ch in (valor or "") if ch.isdigit())


def rifas_schema_ready() -> bool:
    inspector = inspect(db.engine)
    tabelas = set(inspector.get_table_names())
    return {"clientes", "pagamentos", "rifas"}.issubset(tabelas)


def ensure_rifas_schema() -> None:
    if not rifas_schema_ready():
        raise RifaSchemaMissingError(
            "O schema de rifas ainda nao foi criado no banco. Execute 'flask db upgrade' para aplicar as migrations."
        )


def _ensure_inventory(total_numbers: int):
    existentes = db.session.scalar(db.select(func.count(Rifa.id)))
    if existentes and existentes >= total_numbers:
        return

    existentes_numeros = {
        numero for (numero,) in db.session.execute(db.select(Rifa.numero)).all()
    }
    novos = []
    for numero in range(1, total_numbers + 1):
        if numero in existentes_numeros:
            continue
        novos.append(Rifa(numero=numero, status=STATUS_DISPONIVEL))
    if novos:
        db.session.bulk_save_objects(novos)
        db.session.flush()
        logger.info("Estoque de rifas inicializado com %s numero(s).", len(novos))


def _release_expired_reservations():
    reserva_minutos = int(current_app.config["RIFA_RESERVA_MINUTOS"])
    limite = datetime.utcnow() - timedelta(minutes=reserva_minutos)
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
    if not email or "@" not in email:
        raise RifaError("Email invalido.")
    if quantidade_rifas <= 0:
        raise RifaError("Quantidade de rifas deve ser maior que zero.")


def _buscar_ou_criar_cliente(*, nome: str, telefone: str, email: str) -> ClienteRifa:
    cliente = db.session.execute(
        db.select(ClienteRifa).where(ClienteRifa.email == email)
    ).scalar_one_or_none()
    if cliente is None:
        cliente = ClienteRifa(nome=nome, telefone=telefone, email=email)
        db.session.add(cliente)
        db.session.flush()
        return cliente

    cliente.nome = nome
    cliente.telefone = telefone
    return cliente


def purchase_rifas(*, nome: str, telefone: str, email: str, quantidade_rifas: int) -> PurchaseResult:
    ensure_rifas_schema()
    nome = _normalizar_texto(nome)
    email = _normalizar_texto(email).lower()
    telefone = _normalize_phone(telefone)
    _validate_purchase_input(nome, telefone, email, quantidade_rifas)

    gateway = get_pix_gateway()
    valor_unitario = Decimal(str(current_app.config["RIFA_VALOR_UNITARIO"]))
    valor_total = valor_unitario * quantidade_rifas

    with db.session.begin():
        _ensure_inventory(int(current_app.config["RIFA_TOTAL_NUMEROS"]))
        _release_expired_reservations()
        cliente = _buscar_ou_criar_cliente(nome=nome, telefone=telefone, email=email)
        query = (
            db.select(Rifa)
            .where(Rifa.status == STATUS_DISPONIVEL)
            .order_by(Rifa.numero.asc())
            .limit(quantidade_rifas)
        )
        if db.session.bind and db.session.bind.dialect.name != "sqlite":
            query = query.with_for_update(skip_locked=True)
        rifas = db.session.execute(query).scalars().all()
        if len(rifas) < quantidade_rifas:
            raise RifaError("Nao ha quantidade suficiente de rifas disponiveis.")

        charge = gateway.create_charge(
            amount=float(valor_total),
            payer_name=nome,
            payer_email=email,
            description=f"Compra de {quantidade_rifas} rifa(s)",
        )
        pagamento = PagamentoRifa(
            cliente_id=cliente.id,
            valor_total=valor_total,
            quantidade_rifas=quantidade_rifas,
            status="pendente",
            qr_code_base64=charge.qr_code_base64,
            copia_cola_pix=charge.copia_cola_pix,
            external_id=charge.external_id,
        )
        db.session.add(pagamento)
        db.session.flush()

        for rifa in rifas:
            rifa.status = STATUS_RESERVADO
            rifa.cliente_id = cliente.id
            rifa.pagamento_id = pagamento.id

        logger.info(
            "Compra iniciada: pagamento=%s cliente=%s quantidade=%s numeros=%s",
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


def confirm_payment(*, external_id: str | None = None, pagamento_id: str | None = None) -> PagamentoRifa:
    with db.session.begin():
        pagamento = None
        if pagamento_id:
            pagamento = db.session.get(PagamentoRifa, pagamento_id)
        if pagamento is None and external_id:
            pagamento = get_payment_by_external_id(external_id)
        if pagamento is None:
            raise RifaError("Pagamento nao encontrado.")
        if pagamento.status == STATUS_PAGO:
            return pagamento

        pagamento.status = STATUS_PAGO
        pagamento.pago_em = datetime.utcnow()
        for rifa in pagamento.rifas:
            rifa.status = STATUS_PAGO
            rifa.cliente_id = pagamento.cliente_id
            rifa.pagamento_id = pagamento.id

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
        "rifas": rifas,
        "pdf_path": pagamento.pdf_path,
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
        db.select(Rifa).order_by(Rifa.numero.asc())
    ).scalars().all()

    total_pago = sum(float(item.valor_total) for item in pagamentos if item.status == STATUS_PAGO)
    disponiveis = sum(1 for item in rifas if item.status == STATUS_DISPONIVEL)
    reservadas = sum(1 for item in rifas if item.status == STATUS_RESERVADO)
    pagas = sum(1 for item in rifas if item.status == STATUS_PAGO)

    return {
        "pagamentos": pagamentos,
        "clientes": clientes,
        "rifas": rifas,
        "stats": {
            "total_pago": total_pago,
            "disponiveis": disponiveis,
            "reservadas": reservadas,
            "pagas": pagas,
            "clientes": len(clientes),
            "pagamentos": len(pagamentos),
        },
    }
