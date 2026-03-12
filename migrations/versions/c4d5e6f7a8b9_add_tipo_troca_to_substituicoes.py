"""add tipo troca to substituicoes

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5a6
Create Date: 2026-03-12 18:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "substituicoes",
        sa.Column("tipo", sa.String(length=20), nullable=False, server_default="substituicao"),
    )
    op.add_column(
        "substituicoes",
        sa.Column("missa_troca_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_substituicoes_missa_troca_id_missa",
        "substituicoes",
        "missa",
        ["missa_troca_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_substituicoes_tipo"), "substituicoes", ["tipo"], unique=False)
    op.create_index(op.f("ix_substituicoes_missa_troca_id"), "substituicoes", ["missa_troca_id"], unique=False)
    op.alter_column("substituicoes", "tipo", server_default=None)


def downgrade():
    op.drop_index(op.f("ix_substituicoes_missa_troca_id"), table_name="substituicoes")
    op.drop_index(op.f("ix_substituicoes_tipo"), table_name="substituicoes")
    op.drop_constraint("fk_substituicoes_missa_troca_id_missa", "substituicoes", type_="foreignkey")
    op.drop_column("substituicoes", "missa_troca_id")
    op.drop_column("substituicoes", "tipo")
