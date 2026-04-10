import os
from pathlib import Path

import pytest


os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("PIX_PROVIDER", "mock")

from app import create_app
from extensions import db
from models import Ministro, Paroquia


@pytest.fixture
def app():
    temp_dir = Path.cwd() / "instance" / "rifas-tests"
    temp_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "RIFA_PDF_DIR": str(temp_dir),
            "PIX_PROVIDER": "mock",
            "WEBHOOK_SECRET": "segredo-webhook",
            "RIFA_TOTAL_NUMEROS": 30,
            "RIFA_VALOR_UNITARIO": 5,
        }
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
        paroquia = Paroquia(nome="Paroquia Teste")
        db.session.add(paroquia)
        db.session.flush()
        admin = Ministro(
            nome="Admin",
            nome_completo="Admin Teste",
            email="admin@teste.com",
            telefone="11999999999",
            cpf="12345678900",
            tipo="admin",
            pode_logar=True,
            primeiro_acesso=False,
            id_paroquia=paroquia.id,
        )
        admin.set_senha("123456")
        db.session.add(admin)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
