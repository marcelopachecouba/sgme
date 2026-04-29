from dotenv import load_dotenv
load_dotenv()

from app import app
from rifas.payments import SicrediPixGateway



with app.app_context():

    import os

with app.app_context():
    import os

    app.config["SICREDI_CLIENT_ID"] = os.getenv("SICREDI_CLIENT_ID")
    app.config["SICREDI_CLIENT_SECRET"] = os.getenv("SICREDI_CLIENT_SECRET")
    app.config["SICREDI_TOKEN_URL"] = os.getenv("SICREDI_TOKEN_URL")
    app.config["SICREDI_API_URL"] = os.getenv("SICREDI_API_URL")
    app.config["SICREDI_CERT_PATH"] = os.getenv("SICREDI_CERT_PATH")
    app.config["SICREDI_KEY_PATH"] = os.getenv("SICREDI_KEY_PATH")
    app.config["PIX_CHAVE"] = os.getenv("PIX_CHAVE")

    gateway = SicrediPixGateway()

    print("CERT EXISTS:", os.path.exists(os.getenv("SICREDI_CERT_PATH")))
    print("KEY EXISTS:", os.path.exists(os.getenv("SICREDI_KEY_PATH")))
    print("CLIENT_ID:", os.getenv("SICREDI_CLIENT_ID"))
    print("SECRET:", os.getenv("SICREDI_CLIENT_SECRET"))
    print("TOKEN_URL:", os.getenv("SICREDI_TOKEN_URL"))
    print("API_URL:", os.getenv("SICREDI_API_URL"))
    print("CERT:", os.getenv("SICREDI_CERT_PATH"))
    print("KEY:", os.getenv("SICREDI_KEY_PATH"))

    gateway = SicrediPixGateway()

    from decimal import Decimal

    resp = gateway.create_charge(
        amount=Decimal("1.00"),
        payer_name="Teste",
        payer_email="teste@email.com",
        description="Teste integração",
        payer_document="04476385648"  # 👈 CPF aqui
    )
    print(resp)