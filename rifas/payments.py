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
        external_id = uuid.uuid4().hex[:32].upper()
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

    if provider == "sicredi":
        return SicrediPixGateway()

    if provider in {"manual", "mock"}:
        return MockPixGateway()

    # fallback segurança
    logger.warning(f"PIX_PROVIDER desconhecido: {provider}, usando manual.")
    return MockPixGateway()

import requests
import base64
from datetime import datetime, timedelta
from decimal import Decimal
from flask import current_app

import os

class SicrediPixGateway:

    def __init__(self):
        self.client_id = os.getenv("SICREDI_CLIENT_ID")
        self.client_secret = os.getenv("SICREDI_CLIENT_SECRET")
        self.token_url = os.getenv("SICREDI_TOKEN_URL")
        self.base_url = os.getenv("SICREDI_API_URL")
        self.pix_key = os.getenv("PIX_CHAVE")

        cert_path = os.getenv("SICREDI_CERT_PATH")
        key_path = os.getenv("SICREDI_KEY_PATH")

        self.cert = (cert_path, key_path) if cert_path and key_path else None

        # 🔍 DEBUG (pode remover depois)
        print("DEBUG SICREDI INIT:")
        print("CLIENT_ID:", self.client_id)
        print("SECRET:", self.client_secret)
        print("TOKEN_URL:", self.token_url)
        print("API_URL:", self.base_url)
        print("CERT:", cert_path)
        print("KEY:", key_path)
        print("PIX:", self.pix_key)

        # 🔒 VALIDAÇÃO
        if not all([
            self.client_id,
            self.client_secret,
            self.token_url,
            self.base_url,
            self.pix_key,
            cert_path,
            key_path
        ]):
            raise Exception("Configuração Sicredi incompleta")    
        # 🔐 TOKEN CACHE (ESSENCIAL)
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
            logger.error(f"Sicredi erro consulta: {response.text}")
            raise Exception("Erro ao autenticar Sicredi")

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
   
    def create_charge(self, amount, payer_name, payer_email, description, payer_document=None):
        import uuid

        txid = uuid.uuid4().hex[:32].upper()

        # 🔧 monta devedor corretamente
        devedor = {
            "nome": payer_name,
            "email": payer_email or ""
        }

        if payer_document:
            if len(payer_document) == 11:
                devedor["cpf"] = payer_document
            elif len(payer_document) == 14:
                devedor["cnpj"] = payer_document

        # 🔧 payload correto
        payload = {
            "calendario": {
                "expiracao": 3600
            },
            "devedor": devedor,
            "valor": {
                "original": f"{amount:.2f}"
            },
            "chave": self.pix_key,
            "solicitacaoPagador": description
        }

        url = f"{self.base_url}/cob/{txid}"

        try:
            response = requests.put(
                url,
                json=payload,
                headers=self._headers(),
                cert=self.cert,
                timeout=20
            )
        except requests.exceptions.Timeout:
            logger.error("Timeout Sicredi ao criar cobrança")
            raise Exception("Sicredi indisponível")
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro conexão Sicredi: {str(e)}")
            raise Exception("Erro de conexão com Sicredi")

        if response.status_code not in [200, 201]:
            logger.error(f"Sicredi erro cobrança: {response.text}")
            raise Exception("Erro ao criar cobrança Pix")

        data = response.json()

        logger.info(f"Sicredi PIX criado | txid={txid} | valor={amount} | nome={payer_name}")

        # 🔄 buscar cobrança atualizada (forma confiável)
        try:
            cob_response = requests.get(
                f"{self.base_url}/cob/{txid}",
                headers=self._headers(),
                cert=self.cert,
                timeout=20
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao buscar cobrança: {str(e)}")
            raise Exception("Erro ao buscar cobrança Pix")

        if cob_response.status_code != 200:
            logger.error(f"Sicredi erro GET cob: {cob_response.text}")
            raise Exception("Erro ao buscar cobrança")

        cob_data = cob_response.json()

        # 🔎 tenta pegar direto
        pix_copia_cola = cob_data.get("pixCopiaECola")
        qr_base64 = None

        # 🔁 fallback via location
        if not pix_copia_cola:
            location = cob_data.get("loc", {}).get("location")

            if location:
                try:
                    qr_response = requests.get(
                        f"{location}/qrcode",
                        headers=self._headers(),
                        cert=self.cert,
                        timeout=20
                    )

                    if qr_response.status_code == 200:
                        qr_data = qr_response.json()
                        pix_copia_cola = qr_data.get("qrcode")
                        qr_base64 = qr_data.get("imagemQrcode")
                except requests.exceptions.RequestException:
                    pass

        # 🔒 fallback final (não quebra sistema)
        if not pix_copia_cola:
            logger.warning(f"QR ainda não disponível: {cob_data}")

        return PixCharge(
            external_id=txid,
            qr_code_base64=qr_base64,
            copia_cola_pix=pix_copia_cola,
            raw_response=data
        )
    
    # 🔍 ================= CONSULTAR =================
    def get_charge(self, txid: str):
        response = requests.get(
            f"{self.base_url}/cob/{txid}",
            headers=self._headers(),
            cert=self.cert,
            timeout=20
        )

        if response.status_code != 200:
            logger.error(f"Sicredi erro consulta: {response.text}")
            raise Exception("Erro ao autenticar Sicredi")
        return response.json()

    # 🔁 ================= WEBHOOK =================
    def parse_webhook(self, payload: dict):
        """
        Retorna: (txid, status)
        """
        pix_list = payload.get("pix")

        if not isinstance(pix_list, list) or not pix_list:
            logger.warning(f"Webhook inválido (sem pix): {payload}")
            return None, "ignorado"

        pix = pix_list[0]

        #txid = pix.get("txid")
        txid = (pix.get("txid") or "").upper().strip()

        if not txid:
            logger.warning(f"Webhook sem txid: {payload}")
            return None, "ignorado"

        return txid, "pago"

        #return None, "desconhecido"

    # 🔧 ================= UTIL =================
    def _generate_txid(self):
        import uuid
        return uuid.uuid4().hex[:32].upper()
    

    def consultar_cobranca(self, txid):
        url = f"{self.base_url}/cob/{txid}"

        response = requests.get(
            url,
            headers=self._headers(),
            cert=self.cert,
            timeout=20
        )

        if response.status_code != 200:
            return None

        return response.json()


import os
from uuid import uuid4

def gerar_qr_code_arquivo(conteudo):
    import qrcode

    pasta = "static/qrcodes"
    os.makedirs(pasta, exist_ok=True)

    nome = f"{uuid4().hex}.png"
    caminho = os.path.join(pasta, nome)

    img = qrcode.make(conteudo)
    img.save(caminho)

    return f"/static/qrcodes/{nome}"
