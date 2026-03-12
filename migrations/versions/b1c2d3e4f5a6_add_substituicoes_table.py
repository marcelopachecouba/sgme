"""add substituicoes table

Revision ID: b1c2d3e4f5a6
Revises: a4b5c6d7e8f9
Create Date: 2026-03-12 13:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b1c2d3e4f5a6"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "substituicoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("missa_id", sa.Integer(), nullable=False),
        sa.Column("ministro_original_id", sa.Integer(), nullable=False),
        sa.Column("ministro_substituto_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("data_solicitacao", sa.DateTime(), nullable=False),
        sa.Column("data_resposta", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["missa_id"], ["missa.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ministro_original_id"], ["ministro.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ministro_substituto_id"], ["ministro.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_substituicoes_missa_id"), "substituicoes", ["missa_id"], unique=False)
    op.create_index(op.f("ix_substituicoes_ministro_original_id"), "substituicoes", ["ministro_original_id"], unique=False)
    op.create_index(op.f("ix_substituicoes_ministro_substituto_id"), "substituicoes", ["ministro_substituto_id"], unique=False)
    op.create_index(op.f("ix_substituicoes_status"), "substituicoes", ["status"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_substituicoes_status"), table_name="substituicoes")
    op.drop_index(op.f("ix_substituicoes_ministro_substituto_id"), table_name="substituicoes")
    op.drop_index(op.f("ix_substituicoes_ministro_original_id"), table_name="substituicoes")
    op.drop_index(op.f("ix_substituicoes_missa_id"), table_name="substituicoes")
    op.drop_table("substituicoes")
