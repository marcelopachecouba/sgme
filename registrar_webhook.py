from dotenv import load_dotenv
load_dotenv()

import requests
from rifas.payments import SicrediPixGateway

gateway = SicrediPixGateway()

url = f"{gateway.base_url}/webhook/{gateway.pix_key}"

payload = {
    "webhookUrl": "https://sgme.onrender.com/api/webhook/pix/sicredi"
}

response = requests.put(
    url,
    json=payload,
    headers={
        "Authorization": f"Bearer {gateway._get_token()}",
        "Content-Type": "application/json"
    },
    cert=gateway.cert
)

print(response.status_code)
print(response.text)