from dotenv import load_dotenv
load_dotenv()

import requests
from rifas.payments import SicrediPixGateway

gateway = SicrediPixGateway()

url = f"{gateway.base_url}/webhook/{gateway.pix_key}"

headers = {
    "Authorization": f"Bearer {gateway._get_token()}",
    "Content-Type": "application/json"
}

try:
    response = requests.get(
        url,
        headers=headers,
        cert=gateway.cert,
        timeout=20
    )

    print("STATUS:", response.status_code)
    print("RESPOSTA:", response.text)

except Exception as e:
    print("ERRO:", str(e))