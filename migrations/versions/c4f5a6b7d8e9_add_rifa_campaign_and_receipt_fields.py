"""add rifa campaign and payment receipt fields

Revision ID: c4f5a6b7d8e9
Revises: b3ae40e6b330
Create Date: 2026-04-10 19:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
import uuid


revision = "c4f5a6b7d8e9"
down_revision = "b3ae40e6b330"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rifas_campanhas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("titulo", sa.String(length=180), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("data_sorteio", sa.Date(), nullable=False),
        sa.Column("valor_rifa", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantidade_total", sa.Integer(), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_rifas_campanhas_ativa", "rifas_campanhas", ["ativa"])
    op.create_index("ix_rifas_campanhas_created_at", "rifas_campanhas", ["created_at"])
    op.create_index("ix_rifas_campanhas_data_sorteio", "rifas_campanhas", ["data_sorteio"])

    # =========================
    # PAGAMENTOS
    # =========================
    op.add_column("pagamentos", sa.Column("campanha_id", sa.String(length=36), nullable=True))
    op.add_column("pagamentos", sa.Column("comprovante_path", sa.String(length=500)))
    op.add_column("pagamentos", sa.Column("comprovante_nome", sa.String(length=255)))
    op.add_column("pagamentos", sa.Column("comprovante_enviado_em", sa.DateTime()))
    op.add_column("pagamentos", sa.Column("observacoes_admin", sa.Text()))

    op.create_index("ix_pagamentos_campanha_id", "pagamentos", ["campanha_id"])
    op.create_index("ix_pagamentos_comprovante_enviado_em", "pagamentos", ["comprovante_enviado_em"])

    # =========================
    # RIFAS
    # =========================
    op.add_column("rifas", sa.Column("campanha_id", sa.String(length=36), nullable=True))
    op.create_index("ix_rifas_campanha_id", "rifas", ["campanha_id"])

    # =========================
    # CAMPANHA PADRÃO
    # =========================
    default_campaign_id = str(uuid.uuid4())

    op.execute(
        sa.text(
            """
            INSERT INTO rifas_campanhas 
            (id, titulo, descricao, data_sorteio, valor_rifa, quantidade_total, ativa, created_at)
            VALUES 
            (:id, :titulo, :descricao, CURRENT_DATE, :valor_rifa, :quantidade_total, true, CURRENT_TIMESTAMP)
            """
        ).bindparams(
            id=default_campaign_id,
            titulo="Ação entre Fieis",
            descricao="Criada automaticamente",
            valor_rifa=5,
            quantidade_total=100000,
        )
    )

    # =========================
    # ATUALIZA DADOS EXISTENTES
    # =========================
    op.execute(
        sa.text("UPDATE pagamentos SET campanha_id = :id WHERE campanha_id IS NULL")
        .bindparams(id=default_campaign_id)
    )

    op.execute(
        sa.text("UPDATE rifas SET campanha_id = :id WHERE campanha_id IS NULL")
        .bindparams(id=default_campaign_id)
    )

    # =========================
    # AGORA TORNA NOT NULL
    # =========================
    op.alter_column("pagamentos", "campanha_id", nullable=False)
    op.alter_column("rifas", "campanha_id", nullable=False)

    # =========================
    # FOREIGN KEYS
    # =========================
    op.create_foreign_key(
        "fk_pagamentos_campanha_id",
        "pagamentos",
        "rifas_campanhas",
        ["campanha_id"],
        ["id"],
        ondelete="CASCADE"
    )

    op.create_foreign_key(
        "fk_rifas_campanha_id",
        "rifas",
        "rifas_campanhas",
        ["campanha_id"],
        ["id"],
        ondelete="CASCADE"
    )

def downgrade():
    op.drop_constraint("fk_rifas_campanha_id", "rifas", type_="foreignkey")
    op.drop_index(op.f("ix_rifas_campanha_id"), table_name="rifas")
    op.drop_column("rifas", "campanha_id")

    op.drop_constraint("fk_pagamentos_campanha_id", "pagamentos", type_="foreignkey")
    op.drop_index(op.f("ix_pagamentos_comprovante_enviado_em"), table_name="pagamentos")
    op.drop_index(op.f("ix_pagamentos_campanha_id"), table_name="pagamentos")
    op.drop_column("pagamentos", "observacoes_admin")
    op.drop_column("pagamentos", "comprovante_enviado_em")
    op.drop_column("pagamentos", "comprovante_nome")
    op.drop_column("pagamentos", "comprovante_path")
    op.drop_column("pagamentos", "campanha_id")

    op.drop_index(op.f("ix_rifas_campanhas_data_sorteio"), table_name="rifas_campanhas")
    op.drop_index(op.f("ix_rifas_campanhas_created_at"), table_name="rifas_campanhas")
    op.drop_index(op.f("ix_rifas_campanhas_ativa"), table_name="rifas_campanhas")
    op.drop_table("rifas_campanhas")
