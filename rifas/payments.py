import base64
import io
import logging
import uuid
from dataclasses import dataclass

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


class MockPixGateway:
    def create_charge(self, *, amount: float, payer_name: str, payer_email: str, description: str) -> PixCharge:
        external_id = f"mock-{uuid.uuid4()}"
        copia_cola = f"PIX|{external_id}|{amount:.2f}|{payer_name}|{payer_email}|{description}"
        return PixCharge(
            external_id=external_id,
            qr_code_base64=_gerar_qr_code_base64(copia_cola),
            copia_cola_pix=copia_cola,
            raw_response={"provider": "mock", "external_id": external_id},
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
