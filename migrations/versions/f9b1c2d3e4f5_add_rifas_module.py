"""add rifas module

Revision ID: f9b1c2d3e4f5
Revises: e6f7a8b9c0d1
Create Date: 2026-04-10 12:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f9b1c2d3e4f5"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clientes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("telefone", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clientes_nome"), "clientes", ["nome"], unique=False)
    op.create_index(op.f("ix_clientes_telefone"), "clientes", ["telefone"], unique=False)
    op.create_index(op.f("ix_clientes_email"), "clientes", ["email"], unique=False)
    op.create_index(op.f("ix_clientes_created_at"), "clientes", ["created_at"], unique=False)

    op.create_table(
        "pagamentos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("cliente_id", sa.String(length=36), nullable=False),
        sa.Column("valor_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantidade_rifas", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("qr_code_base64", sa.Text(), nullable=True),
        sa.Column("copia_cola_pix", sa.Text(), nullable=True),
        sa.Column("external_id", sa.String(length=120), nullable=True),
        sa.Column("pdf_path", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("pago_em", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
    )
    op.create_index(op.f("ix_pagamentos_cliente_id"), "pagamentos", ["cliente_id"], unique=False)
    op.create_index(op.f("ix_pagamentos_status"), "pagamentos", ["status"], unique=False)
    op.create_index(op.f("ix_pagamentos_external_id"), "pagamentos", ["external_id"], unique=False)
    op.create_index(op.f("ix_pagamentos_created_at"), "pagamentos", ["created_at"], unique=False)
    op.create_index(op.f("ix_pagamentos_pago_em"), "pagamentos", ["pago_em"], unique=False)

    op.create_table(
        "rifas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cliente_id", sa.String(length=36), nullable=True),
        sa.Column("pagamento_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"]),
        sa.ForeignKeyConstraint(["pagamento_id"], ["pagamentos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("numero"),
    )
    op.create_index(op.f("ix_rifas_numero"), "rifas", ["numero"], unique=False)
    op.create_index(op.f("ix_rifas_status"), "rifas", ["status"], unique=False)
    op.create_index(op.f("ix_rifas_cliente_id"), "rifas", ["cliente_id"], unique=False)
    op.create_index(op.f("ix_rifas_pagamento_id"), "rifas", ["pagamento_id"], unique=False)
    op.create_index(op.f("ix_rifas_created_at"), "rifas", ["created_at"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_rifas_created_at"), table_name="rifas")
    op.drop_index(op.f("ix_rifas_pagamento_id"), table_name="rifas")
    op.drop_index(op.f("ix_rifas_cliente_id"), table_name="rifas")
    op.drop_index(op.f("ix_rifas_status"), table_name="rifas")
    op.drop_index(op.f("ix_rifas_numero"), table_name="rifas")
    op.drop_table("rifas")

    op.drop_index(op.f("ix_pagamentos_pago_em"), table_name="pagamentos")
    op.drop_index(op.f("ix_pagamentos_created_at"), table_name="pagamentos")
    op.drop_index(op.f("ix_pagamentos_external_id"), table_name="pagamentos")
    op.drop_index(op.f("ix_pagamentos_status"), table_name="pagamentos")
    op.drop_index(op.f("ix_pagamentos_cliente_id"), table_name="pagamentos")
    op.drop_table("pagamentos")

    op.drop_index(op.f("ix_clientes_created_at"), table_name="clientes")
    op.drop_index(op.f("ix_clientes_email"), table_name="clientes")
    op.drop_index(op.f("ix_clientes_telefone"), table_name="clientes")
    op.drop_index(op.f("ix_clientes_nome"), table_name="clientes")
    op.drop_table("clientes")
