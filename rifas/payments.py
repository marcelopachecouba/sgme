import base64
import io
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import qrcode
import requests
from flask import current_app
from rifas.sicoob_service import get_sicoob_token

logger = logging.getLogger(__name__)


@dataclass
class PixCharge:
    external_id: str
    qr_code_base64: str
    copia_cola_pix: str
    raw_response: dict


def _gerar_qr_code_base64(conteudo):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(conteudo)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")

    return base64.b64encode(buffer.getvalue()).decode()


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


def generate_pix_payload(key, amount, txid):
    from decimal import Decimal, ROUND_HALF_UP

    def f(id, value):
        return f"{id}{len(value):02}{value}"

    key = ''.join(key.strip().split())

    merchant_name = "PAROQUIA NOSSA SENHORA APARECIDA"[:25]
    merchant_city = "PALMAS"[:15]

    amount = Decimal(str(amount)).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

    if amount <= 0:
        raise ValueError("Valor do PIX deve ser maior que zero")

    amount_str = f"{amount:.2f}"

    # ✅ FUNÇÃO CORRETA
    def build_merchant_account(key):
        gui = f("00", "br.gov.bcb.pix")
        chave = f("01", key)

        conteudo = gui + chave
        return f"26{len(conteudo):02}{conteudo}"

    # ✅ AGORA SIM USANDO
    merchant_account = build_merchant_account(key)

    # ✅ FORA da função (CORRETO)
    txid = ''.join(filter(str.isalnum, txid)).upper()[:25]
    additional = f("62", f("05", txid))

    payload = (
        f("00", "01") +
        f("01", "12") +
        merchant_account +
        f("52", "0000") +
        f("53", "986") +
        f("54", amount_str) +
        f("58", "BR") +
        f("59", merchant_name) +
        f("60", merchant_city) +
        additional +
        "6304"
    )

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
        external_id = uuid.uuid4().hex[:25].upper()
        chave_pix = current_app.config.get("PIX_CHAVE", "01172466000480")
        copia_cola = generate_pix_payload(
            key=chave_pix,
            amount=amount,
            txid=external_id
        )       
        print("PIX REAL GERADO >>>", copia_cola)

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
    provider = (current_app.config.get("PIX_PROVIDER", "manual") or "manual").strip().lower()

    if provider == "mercadopago":
        access_token = current_app.config.get("PIX_ACCESS_TOKEN") or current_app.config.get("PIX_API_KEY")
        if not access_token:
            logger.warning("PIX_ACCESS_TOKEN nao configurado; usando manual.")
            return MockPixGateway()
        return MercadoPagoPixGateway(access_token)

    if provider == "sicoob":
        return SicrediPixGateway()

    if provider in {"manual", "mock"}:
        return MockPixGateway()

    # fallback segurança
    logger.warning(f"PIX_PROVIDER desconhecido: {provider}, usando manual.")
    return MockPixGateway()


class SicoobPixGateway:

    def parse_webhook(self, payload: dict):
        pix_list = payload.get("pix", [])

        if not pix_list:
            return None, None

        pix = pix_list[0]
        txid = pix.get("txid")

        return txid, "pago"

    def create_charge(self, *, amount, payer_name, payer_email, description):
        token = get_sicoob_token()

        base_url = current_app.config.get("SICOOB_BASE_URL")
        chave_pix = current_app.config.get("PIX_CHAVE")

        cert_path = current_app.config.get("SICOOB_CERT_PATH")
        key_path = current_app.config.get("SICOOB_KEY_PATH")

        if not all([base_url, chave_pix, cert_path, key_path]):
            raise Exception("Configuração do Sicoob incompleta.")

        txid = uuid.uuid4().hex[:25].upper()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        cert = (cert_path, key_path)

        # 🔥 1. CRIAR COBRANÇA
        url = f"{base_url}/cob/{txid}"

        payload = {
            "calendario": {"expiracao": 3600},
            "valor": {"original": f"{float(amount):.2f}"},
            "chave": chave_pix,
            "solicitacaoPagador": description[:140]
        }

        response = requests.put(
            url,
            json=payload,
            headers=headers,
            cert=cert,
            timeout=30
        )

        if response.status_code not in (200, 201):
            raise Exception(f"Erro ao criar cobrança Sicoob: {response.text}")

        # 🔥 2. GERAR QR CODE
        url_qr = f"{base_url}/cob/{txid}/qrcode"

        response_qr = requests.get(
            url_qr,
            headers=headers,
            cert=cert,
            timeout=30
        )

        if response_qr.status_code != 200:
            raise Exception(f"Erro ao gerar QR Code Sicoob: {response_qr.text}")

        data = response_qr.json()

        return PixCharge(
            external_id=txid,
            qr_code_base64=data.get("imagemQrcode", ""),
            copia_cola_pix=data.get("qrCode", ""),
            raw_response=data
        )

import requests
import base64
from datetime import datetime, timedelta
from decimal import Decimal
from flask import current_app

class SicrediPixGateway:

    def __init__(self):
        self.client_id = current_app.config.get("SICREDI_CLIENT_ID")
        self.client_secret = current_app.config.get("SICREDI_CLIENT_SECRET")
        self.token_url = current_app.config.get("SICREDI_TOKEN_URL")
        self.base_url = current_app.config.get("SICREDI_API_URL")

        self.pix_key = current_app.config.get("PIX_CHAVE")

        self.cert = (
            current_app.config.get("SICREDI_CERT_PATH"),
            current_app.config.get("SICREDI_KEY_PATH"),
        )

        self._token = None
        self._token_expira = None

    # 🔐 ================= TOKEN =================
    def _get_token(self):
        if self._token and self._token_expira and datetime.utcnow() < self._token_expira:
            return self._token

        response = requests.post(
            self.token_url,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
            cert=self.cert,
            timeout=20,
        )

        if response.status_code != 200:
            raise Exception(f"Erro ao obter token Sicredi: {response.text}")

        data = response.json()

        self._token = data["access_token"]
        self._token_expira = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 300) - 30)

        return self._token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    # 💰 ================= CRIAR COBRANÇA =================
    def create_charge(self, amount: Decimal, payer_name: str, payer_email: str, description: str):
        txid = self._generate_txid()

        payload = {
            "calendario": {
                "expiracao": 3600
            },
            "devedor": {
                "nome": payer_name,
                "email": payer_email or ""
            },
            "valor": {
                "original": f"{amount:.2f}"
            },
            "chave": self.pix_key,
            "solicitacaoPagador": description
        }

        url = f"{self.base_url}/v2/cob/{txid}"

        response = requests.put(
            url,
            json=payload,
            headers=self._headers(),
            cert=self.cert,
            timeout=20
        )

        if response.status_code not in [200, 201]:
            raise Exception(f"Erro ao criar cobrança Pix: {response.text}")

        data = response.json()

        # 🔥 gerar QR Code via endpoint
        loc_id = data.get("loc", {}).get("id")

        qr_response = requests.get(
            f"{self.base_url}/v2/loc/{loc_id}/qrcode",
            headers=self._headers(),
            cert=self.cert,
            timeout=20
        )

        if qr_response.status_code != 200:
            raise Exception("Erro ao gerar QR Code")

        qr_data = qr_response.json()

        return type("Charge", (), {
            "qr_code_base64": qr_data.get("imagemQrcode"),
            "copia_cola_pix": qr_data.get("qrcode"),
            "external_id": txid
        })

    # 🔍 ================= CONSULTAR =================
    def get_charge(self, txid: str):
        response = requests.get(
            f"{self.base_url}/v2/cob/{txid}",
            headers=self._headers(),
            cert=self.cert,
            timeout=20
        )

        if response.status_code != 200:
            raise Exception(f"Erro ao consultar cobrança: {response.text}")

        return response.json()

    # 🔁 ================= WEBHOOK =================
    def parse_webhook(self, payload: dict):
        """
        Retorna: (txid, status)
        """
        if "pix" in payload:
            pix = payload["pix"][0]
            txid = pix.get("txid")
            return txid, "pago"

        return None, "desconhecido"

    # 🔧 ================= UTIL =================
    def _generate_txid(self):
        import uuid
        return uuid.uuid4().hex[:25].upper()
