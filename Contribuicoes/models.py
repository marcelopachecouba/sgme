from datetime import datetime

from extensions import db


class CategoriaContribuicao(db.Model):
    __tablename__ = "categoria_contribuicao"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30), unique=True, nullable=False, index=True)
    descricao = db.Column(db.String(80), nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)

    contribuicoes = db.relationship("Contribuicao", back_populates="categoria", lazy="dynamic")

    def __repr__(self):
        return self.descricao


class Dizimista(db.Model):
    __tablename__ = "dizimista"

    id = db.Column(db.Integer, primary_key=True)
    cpf = db.Column(db.String(14), unique=True, nullable=False, index=True)
    nome = db.Column(db.String(150), nullable=False, index=True)
    telefone = db.Column(db.String(20))
    whatsapp = db.Column(db.String(20))
    email = db.Column(db.String(120))
    cep = db.Column(db.String(10))
    endereco = db.Column(db.String(200))
    numero = db.Column(db.String(20))
    bairro = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    comunidade_id = db.Column(db.Integer, db.ForeignKey("comunidades.id"), index=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    comunidade = db.relationship("Comunidade", lazy="joined")
    contribuicoes = db.relationship("Contribuicao", back_populates="dizimista", lazy="dynamic")

    def __repr__(self):
        return self.nome


class Contribuicao(db.Model):
    __tablename__ = "contribuicao"

    id = db.Column(db.Integer, primary_key=True)
    dizimista_id = db.Column(db.Integer, db.ForeignKey("dizimista.id"), nullable=False, index=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categoria_contribuicao.id"), nullable=False, index=True)
    comunidade_id = db.Column(db.Integer, db.ForeignKey("comunidades.id"), index=True)
    competencia = db.Column(db.String(7), index=True)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    descricao = db.Column(db.String(180))

    txid = db.Column(db.String(35), unique=True, index=True)
    external_id = db.Column(db.String(120), index=True)
    qr_code_base64 = db.Column(db.Text)
    copia_cola_pix = db.Column(db.Text)
    chave_pix = db.Column(db.String(150))

    endtoendid = db.Column(db.String(100), index=True)
    codigo_autenticacao = db.Column(db.String(100))
    pagador = db.Column(db.String(150))
    cpf_pagador = db.Column(db.String(20))
    payload = db.Column(db.JSON)
    banco_payload = db.Column(db.Text)

    status = db.Column(db.String(20), default="pendente", nullable=False, index=True)
    origem_pagamento = db.Column(db.String(30), default="pix_auto")
    data_geracao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    data_pagamento = db.Column(db.DateTime, index=True)
    cancelado_em = db.Column(db.DateTime)

    dizimista = db.relationship("Dizimista", back_populates="contribuicoes", lazy="joined")
    categoria = db.relationship("CategoriaContribuicao", back_populates="contribuicoes", lazy="joined")
    comunidade = db.relationship("Comunidade", lazy="joined")
    recibo = db.relationship("ReciboContribuicao", back_populates="contribuicao", uselist=False)

    __table_args__ = (
        db.Index("idx_contribuicao_txid_status", "txid", "status"),
        db.Index("idx_contribuicao_periodo", "data_pagamento", "categoria_id"),
    )


class ReciboContribuicao(db.Model):
    __tablename__ = "recibo_contribuicao"

    id = db.Column(db.Integer, primary_key=True)
    contribuicao_id = db.Column(db.Integer, db.ForeignKey("contribuicao.id"), nullable=False, unique=True)
    numero = db.Column(db.String(30), unique=True, nullable=False)
    data_emissao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    observacao = db.Column(db.Text)
    pdf_path = db.Column(db.String(500))

    contribuicao = db.relationship("Contribuicao", back_populates="recibo", lazy="joined")
