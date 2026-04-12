import hashlib
import hmac
import io
import json
from pathlib import Path

from extensions import db
from models import PagamentoRifa, Rifa


def test_compra_de_rifa_reserva_numeros_e_gera_pix(client, app):
    response = client.post(
        "/rifas/comprar",
        json={
            "nome": "Maria",
            "telefone": "(11) 99999-1111",
            "email": "maria@example.com",
            "quantidade_rifas": 3,
        },
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "pendente"
    assert data["campanha_titulo"] == "Rifa Teste"
    assert len(data["numeros"]) == 3
    assert data["qr_code_base64"]
    assert data["copia_cola_pix"]

    with app.app_context():
        pagamento = db.session.get(PagamentoRifa, data["pagamento_id"])
        assert pagamento is not None
        assert pagamento.status == "pendente"
        rifas = Rifa.query.filter_by(pagamento_id=pagamento.id).all()
        assert len(rifas) == 3
        assert all(rifa.status == "reservado" for rifa in rifas)


def test_upload_de_comprovante(client, app):
    compra = client.post(
        "/rifas/comprar",
        json={
            "nome": "Maria",
            "telefone": "(11) 99999-1111",
            "email": "maria@example.com",
            "quantidade_rifas": 1,
        },
    ).get_json()

    response = client.post(
        f"/rifas/pagamento/{compra['pagamento_id']}/comprovante",
        data={"comprovante": (io.BytesIO(b"arquivo-teste"), "comprovante.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["comprovante_path"]


def test_webhook_confirma_pagamento_e_gera_pdf(client, app):
    compra = client.post(
        "/rifas/comprar",
        json={
            "nome": "Joao",
            "telefone": "11999998888",
            "email": "joao@example.com",
            "quantidade_rifas": 2,
        },
    ).get_json()

    payload = {"external_id": compra["external_id"], "status": "pago"}
    raw_body = json.dumps(payload).encode("utf-8")
    assinatura = hmac.new(b"segredo-webhook", raw_body, hashlib.sha256).hexdigest()
    response = client.post(
        "/rifas/webhook/pix",
        data=raw_body,
        content_type="application/json",
        headers={"X-Webhook-Signature": assinatura},
    )

    assert response.status_code == 200

    with app.app_context():
        pagamento = db.session.get(PagamentoRifa, compra["pagamento_id"])
        assert pagamento.status == "pago"
        assert pagamento.pdf_path
        assert Path(pagamento.pdf_path).exists()
        rifas = Rifa.query.filter_by(pagamento_id=pagamento.id).all()
        assert all(rifa.status == "pago" for rifa in rifas)


def test_consulta_pagamento_retorna_resumo(client):
    compra = client.post(
        "/rifas/comprar",
        json={
            "nome": "Clara",
            "telefone": "11988887777",
            "email": "clara@example.com",
            "quantidade_rifas": 1,
        },
    ).get_json()

    response = client.get(f"/rifas/pagamento/{compra['pagamento_id']}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == compra["pagamento_id"]
    assert data["cliente"]["nome"] == "Clara"
    assert data["campanha"]["titulo"] == "Rifa Teste"
    assert len(data["rifas"]) == 1
