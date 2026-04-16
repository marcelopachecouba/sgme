import time
import requests
from flask import current_app

# 🔁 cache simples em memória
_sicoob_token_cache = {
    "access_token": None,
    "expires_at": 0
}

def get_sicoob_token():
    global _sicoob_token_cache

    # ⏱️ se ainda válido, reutiliza
    if _sicoob_token_cache["access_token"] and time.time() < _sicoob_token_cache["expires_at"]:
        return _sicoob_token_cache["access_token"]

    client_id = current_app.config.get("SICOOB_CLIENT_ID")
    client_secret = current_app.config.get("SICOOB_CLIENT_SECRET")
    token_url = current_app.config.get("SICOOB_TOKEN_URL")

    cert_path = current_app.config.get("SICOOB_CERT_PATH")
    key_path = current_app.config.get("SICOOB_KEY_PATH")

    if not all([client_id, client_secret, token_url, cert_path, key_path]):
        raise Exception("Configuração do Sicoob incompleta.")

    response = requests.post(
        token_url,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        cert=(cert_path, key_path),  # 🔐 mTLS obrigatório
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(f"Erro ao obter token Sicoob: {response.text}")

    data = response.json()

    access_token = data.get("access_token")
    expires_in = data.get("expires_in", 300)

    if not access_token:
        raise Exception("Token não retornado pelo Sicoob.")

    # ⏱️ guarda com margem de segurança
    _sicoob_token_cache["access_token"] = access_token
    _sicoob_token_cache["expires_at"] = time.time() + int(expires_in) - 60

    return access_token