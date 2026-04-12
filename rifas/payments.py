import base64
import io
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

import qrcode
import requests
from flask import current_app


logger = logging.getLogger(__name__)


@dataclass
class PixCharge:
    external_id: str
    qr_code_base64: str
    copia_cola_pix: str
    raw_response: dict


def _gerar_qr_code_base64(conteudo: str) -> str:
    imagem = qrcode.make(conteudo)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _pix_field(field_id: str, value: str) -> str:
    return f"{field_id}{len(value):02d}{value}"


def _crc16(payload: str) -> str:
    polynomial = 0x1021
    result = 0xFFFF
    for char in payload:
        result ^= ord(char) << 8
        for _ in range(8):
            if result & 0x8000:
                result = (result << 1) ^ polynomial
            else:
                result <<= 1
            result &= 0xFFFF
    return f"{result:04X}"


def generate_pix_payload(*, key: str, amount: float, txid: str) -> str:
    from decimal import Decimal, ROUND_HALF_UP

    key = key.strip()

    def f(id, v):
        return f"{id}{len(v):02}{v}"

    # 🔧 DADOS
    merchant_name = "PAROQUIA NS APARECIDA"[:25]
    merchant_city = "PALMAS"[:15]
    amount = f"{Decimal(str(amount)).quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)}"

    # 🔧 TXID LIMPO (SEM mock!)
    txid = ''.join(filter(str.isalnum, txid))[:25]
    if not txid:
        txid = "SGME123456789"

    # 🔧 CAMPOS
    gui = "0013br.gov.bcb.pix"
    chave = f"01{len(key):02}{key}"

    merchant_account_info = gui + chave

    # 🔥 FORÇANDO TAMANHO CORRETO
    tamanho = len(merchant_account_info)

    merchant_account = f"26{tamanho:02}{merchant_account_info}"

    additional_data = f("62", f("05", txid))

    payload = (
        f("00", "01") +
        f("01", "11") +
        merchant_account +
        f("52", "0000") +
        f("53", "986") +
        f("54", amount) +
        f("58", "BR") +
        f("59", merchant_name) +
        f("60", merchant_city) +
        additional_data +
        "6304"
    )

    # 🔐 CRC
    def crc16(payload):
        polinomio = 0x1021
        resultado = 0xFFFF
        for c in payload:
            resultado ^= ord(c) << 8
            for _ in range(8):
                if resultado & 0x8000:
                    resultado = (resultado << 1) ^ polinomio
                else:
                    resultado <<= 1
                resultado &= 0xFFFF
        return f"{resultado:04X}"

    return payload + crc16(payload)

class MockPixGateway:
    def create_charge(self, *, amount: float, payer_name: str, payer_email: str, description: str) -> PixCharge:
        external_id = uuid.uuid4().hex
        chave_pix = current_app.config.get("PIX_CHAVE", "63999430482")
        copia_cola = generate_pix_payload(
            key=chave_pix,
            amount=amount,
            txid=external_id
        )        
        return PixCharge(
            external_id=external_id,
            qr_code_base64=_gerar_qr_code_base64(copia_cola),
            copia_cola_pix=copia_cola,
            raw_response={
                "provider": "mock",
                "external_id": external_id,
                "payer_name": payer_name,
                "payer_email": payer_email,
                "pix_key": chave_pix,
            },
        )

    def parse_webhook(self, payload: dict) -> tuple[str | None, str]:
        return payload.get("external_id"), payload.get("status", "pago")


class MercadoPagoPixGateway:
    endpoint = "https://api.mercadopago.com/v1/payments"

    def __init__(self, access_token: str):
        self.access_token = access_token

    def create_charge(self, *, amount: float, payer_name: str, payer_email: str, description: str) -> PixCharge:
        idempotency_key = str(uuid.uuid4())
        body = {
            "transaction_amount": round(amount, 2),
            "description": description,
            "payment_method_id": "pix",
            "payer": {
                "email": payer_email,
                "first_name": payer_name[:120],
            },
        }
        response = requests.post(
            self.endpoint,
            json=body,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "X-Idempotency-Key": idempotency_key,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        tx_data = (data.get("point_of_interaction") or {}).get("transaction_data") or {}
        copia_cola = tx_data.get("qr_code", "")
        qr_code_base64 = tx_data.get("qr_code_base64") or _gerar_qr_code_base64(copia_cola)
        return PixCharge(
            external_id=str(data.get("id")),
            qr_code_base64=qr_code_base64,
            copia_cola_pix=copia_cola,
            raw_response=data,
        )

    def parse_webhook(self, payload: dict) -> tuple[str | None, str]:
        data = payload.get("data") or {}
        status = payload.get("status") or payload.get("action") or "pago"
        external_id = data.get("id") or payload.get("external_id")
        return None if external_id is None else str(external_id), str(status).lower()


def get_pix_gateway():
    provider = current_app.config.get("PIX_PROVIDER", "mock")
    if provider == "mercadopago":
        access_token = current_app.config.get("PIX_ACCESS_TOKEN") or current_app.config.get("PIX_API_KEY")
        if not access_token:
            logger.warning("PIX_ACCESS_TOKEN/PIX_API_KEY nao configurado; usando gateway mock.")
            return MockPixGateway()
        return MercadoPagoPixGateway(access_token)
    return MockPixGateway()
