"""add contribuicoes module

Revision ID: 20260616_contrib
Revises: c65e710e888b
Create Date: 2026-06-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260616_contrib"
down_revision = "c65e710e888b"
branch_labels = None
depends_on = None


def _table_exists(inspector, name):
    return name in inspector.get_table_names()


def _column_exists(inspector, table, column):
    return column in {item["name"] for item in inspector.get_columns(table)}


def _add_column_if_missing(inspector, table, column):
    if not _column_exists(inspector, table, column.name):
        op.add_column(table, column)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "categoria_contribuicao"):
        op.create_table(
            "categoria_contribuicao",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("codigo", sa.String(length=30), nullable=False),
            sa.Column("descricao", sa.String(length=80), nullable=False),
            sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        op.create_index("ix_categoria_contribuicao_codigo", "categoria_contribuicao", ["codigo"], unique=True)
    else:
        _add_column_if_missing(inspector, "categoria_contribuicao", sa.Column("codigo", sa.String(length=30)))
        _add_column_if_missing(inspector, "categoria_contribuicao", sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()))
        try:
            op.create_index("ix_categoria_contribuicao_codigo", "categoria_contribuicao", ["codigo"], unique=True)
        except Exception:
            pass

    if not _table_exists(inspector, "dizimista"):
        op.create_table(
            "dizimista",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("cpf", sa.String(length=14), nullable=False),
            sa.Column("nome", sa.String(length=150), nullable=False),
            sa.Column("telefone", sa.String(length=20)),
            sa.Column("whatsapp", sa.String(length=20)),
            sa.Column("email", sa.String(length=120)),
            sa.Column("cep", sa.String(length=10)),
            sa.Column("endereco", sa.String(length=200)),
            sa.Column("numero", sa.String(length=20)),
            sa.Column("bairro", sa.String(length=100)),
            sa.Column("cidade", sa.String(length=100)),
            sa.Column("comunidade_id", sa.Integer(), sa.ForeignKey("comunidades.id")),
            sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("data_cadastro", sa.DateTime(), nullable=False),
            sa.Column("atualizado_em", sa.DateTime()),
        )
        op.create_index("ix_dizimista_cpf", "dizimista", ["cpf"], unique=True)
        op.create_index("ix_dizimista_nome", "dizimista", ["nome"])
    else:
        for column in [
            sa.Column("atualizado_em", sa.DateTime()),
            sa.Column("whatsapp", sa.String(length=20)),
            sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        ]:
            _add_column_if_missing(inspector, "dizimista", column)

    if not _table_exists(inspector, "contribuicao"):
        op.create_table(
            "contribuicao",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("dizimista_id", sa.Integer(), sa.ForeignKey("dizimista.id"), nullable=False),
            sa.Column("categoria_id", sa.Integer(), sa.ForeignKey("categoria_contribuicao.id"), nullable=False),
            sa.Column("comunidade_id", sa.Integer(), sa.ForeignKey("comunidades.id")),
            sa.Column("competencia", sa.String(length=7)),
            sa.Column("valor", sa.Numeric(10, 2), nullable=False),
            sa.Column("descricao", sa.String(length=180)),
            sa.Column("txid", sa.String(length=35)),
            sa.Column("external_id", sa.String(length=120)),
            sa.Column("qr_code_base64", sa.Text()),
            sa.Column("copia_cola_pix", sa.Text()),
            sa.Column("chave_pix", sa.String(length=150)),
            sa.Column("endtoendid", sa.String(length=100)),
            sa.Column("codigo_autenticacao", sa.String(length=100)),
            sa.Column("pagador", sa.String(length=150)),
            sa.Column("cpf_pagador", sa.String(length=20)),
            sa.Column("payload", sa.JSON()),
            sa.Column("banco_payload", sa.Text()),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pendente"),
            sa.Column("origem_pagamento", sa.String(length=30), server_default="pix_auto"),
            sa.Column("data_geracao", sa.DateTime(), nullable=False),
            sa.Column("data_pagamento", sa.DateTime()),
            sa.Column("cancelado_em", sa.DateTime()),
        )
        op.create_index("ix_contribuicao_txid", "contribuicao", ["txid"], unique=True)
        op.create_index("idx_contribuicao_txid_status", "contribuicao", ["txid", "status"])
        op.create_index("idx_contribuicao_periodo", "contribuicao", ["data_pagamento", "categoria_id"])
    else:
        for column in [
            sa.Column("descricao", sa.String(length=180)),
            sa.Column("external_id", sa.String(length=120)),
            sa.Column("qr_code_base64", sa.Text()),
            sa.Column("copia_cola_pix", sa.Text()),
            sa.Column("banco_payload", sa.Text()),
            sa.Column("origem_pagamento", sa.String(length=30), server_default="pix_auto"),
            sa.Column("cancelado_em", sa.DateTime()),
        ]:
            _add_column_if_missing(inspector, "contribuicao", column)

    if not _table_exists(inspector, "recibo_contribuicao"):
        op.create_table(
            "recibo_contribuicao",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("contribuicao_id", sa.Integer(), sa.ForeignKey("contribuicao.id"), nullable=False, unique=True),
            sa.Column("numero", sa.String(length=30), nullable=False, unique=True),
            sa.Column("data_emissao", sa.DateTime(), nullable=False),
            sa.Column("observacao", sa.Text()),
            sa.Column("pdf_path", sa.String(length=500)),
        )
    else:
        _add_column_if_missing(inspector, "recibo_contribuicao", sa.Column("pdf_path", sa.String(length=500)))

    op.execute("""
        INSERT INTO categoria_contribuicao (codigo, descricao, ativo)
        VALUES
            ('dizimo', 'Dizimo', true),
            ('doacao', 'Doacao', true),
            ('oferta', 'Oferta', true),
            ('campanha', 'Campanha', true),
            ('construcao', 'Fundo de Construcao', true),
            ('evangelizacao', 'Evangelizacao', true)
        ON CONFLICT (codigo) DO UPDATE
        SET descricao = EXCLUDED.descricao, ativo = true
    """)


def downgrade():
    op.drop_table("recibo_contribuicao")
    op.drop_table("contribuicao")
    op.drop_table("dizimista")
    op.drop_table("categoria_contribuicao")
