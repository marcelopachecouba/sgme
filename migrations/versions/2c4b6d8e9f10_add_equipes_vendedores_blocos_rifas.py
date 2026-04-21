"""add equipes vendedores blocos rifas

Revision ID: 2c4b6d8e9f10
Revises: 89706e882cb2
Create Date: 2026-04-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2c4b6d8e9f10"
down_revision = "89706e882cb2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "equipes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome"),
    )
    op.create_index(op.f("ix_equipes_ativa"), "equipes", ["ativa"], unique=False)
    op.create_index(op.f("ix_equipes_created_at"), "equipes", ["created_at"], unique=False)

    op.create_table(
        "vendedores",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("equipe_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["equipe_id"], ["equipes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_index(op.f("ix_vendedores_codigo"), "vendedores", ["codigo"], unique=False)
    op.create_index(op.f("ix_vendedores_created_at"), "vendedores", ["created_at"], unique=False)
    op.create_index(op.f("ix_vendedores_equipe_id"), "vendedores", ["equipe_id"], unique=False)

    op.create_table(
        "blocos_rifas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campanha_id", sa.String(length=36), nullable=False),
        sa.Column("vendedor_codigo", sa.String(length=50), nullable=False),
        sa.Column("numero_inicio", sa.Integer(), nullable=False),
        sa.Column("numero_fim", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("numero_inicio <= numero_fim", name="ck_bloco_rifa_intervalo"),
        sa.ForeignKeyConstraint(["campanha_id"], ["rifas_campanhas.id"]),
        sa.ForeignKeyConstraint(["vendedor_codigo"], ["vendedores.codigo"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campanha_id",
            "numero_inicio",
            "numero_fim",
            name="uq_bloco_rifa_intervalo_campanha",
        ),
    )
    op.create_index(op.f("ix_blocos_rifas_campanha_id"), "blocos_rifas", ["campanha_id"], unique=False)
    op.create_index(op.f("ix_blocos_rifas_created_at"), "blocos_rifas", ["created_at"], unique=False)
    op.create_index(op.f("ix_blocos_rifas_vendedor_codigo"), "blocos_rifas", ["vendedor_codigo"], unique=False)

    with op.batch_alter_table("pagamentos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("vendedor_codigo", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("equipe_id", sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f("ix_pagamentos_vendedor_codigo"), ["vendedor_codigo"], unique=False)
        batch_op.create_index(batch_op.f("ix_pagamentos_equipe_id"), ["equipe_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_pagamentos_vendedor_codigo_vendedores",
            "vendedores",
            ["vendedor_codigo"],
            ["codigo"],
        )
        batch_op.create_foreign_key(
            "fk_pagamentos_equipe_id_equipes",
            "equipes",
            ["equipe_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("pagamentos", schema=None) as batch_op:
        batch_op.drop_constraint("fk_pagamentos_equipe_id_equipes", type_="foreignkey")
        batch_op.drop_constraint("fk_pagamentos_vendedor_codigo_vendedores", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_pagamentos_equipe_id"))
        batch_op.drop_index(batch_op.f("ix_pagamentos_vendedor_codigo"))
        batch_op.drop_column("equipe_id")
        batch_op.drop_column("vendedor_codigo")

    op.drop_index(op.f("ix_blocos_rifas_vendedor_codigo"), table_name="blocos_rifas")
    op.drop_index(op.f("ix_blocos_rifas_created_at"), table_name="blocos_rifas")
    op.drop_index(op.f("ix_blocos_rifas_campanha_id"), table_name="blocos_rifas")
    op.drop_table("blocos_rifas")

    op.drop_index(op.f("ix_vendedores_equipe_id"), table_name="vendedores")
    op.drop_index(op.f("ix_vendedores_created_at"), table_name="vendedores")
    op.drop_index(op.f("ix_vendedores_codigo"), table_name="vendedores")
    op.drop_table("vendedores")

    op.drop_index(op.f("ix_equipes_created_at"), table_name="equipes")
    op.drop_index(op.f("ix_equipes_ativa"), table_name="equipes")
    op.drop_table("equipes")
