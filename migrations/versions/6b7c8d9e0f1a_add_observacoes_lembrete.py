"""add observacoes lembrete

Revision ID: 6b7c8d9e0f1a
Revises: 5dde2ae35a99
Create Date: 2026-04-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "6b7c8d9e0f1a"
down_revision = "5dde2ae35a99"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "OBSERVACOES_LEMBRETE",
        sa.Column("ID", sa.Integer(), nullable=False),
        sa.Column("DESCRICAO", sa.Text(), nullable=False),
        sa.Column("ATIVO", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("DATA_CADASTRO", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("ID"),
    )
    op.create_index(op.f("ix_OBSERVACOES_LEMBRETE_ATIVO"), "OBSERVACOES_LEMBRETE", ["ATIVO"], unique=False)
    op.create_index(op.f("ix_OBSERVACOES_LEMBRETE_DATA_CADASTRO"), "OBSERVACOES_LEMBRETE", ["DATA_CADASTRO"], unique=False)
    op.create_index(op.f("ix_OBSERVACOES_LEMBRETE_id_paroquia"), "OBSERVACOES_LEMBRETE", ["id_paroquia"], unique=False)
    op.alter_column("OBSERVACOES_LEMBRETE", "ATIVO", server_default=None)
    op.alter_column("OBSERVACOES_LEMBRETE", "DATA_CADASTRO", server_default=None)


def downgrade():
    op.drop_index(op.f("ix_OBSERVACOES_LEMBRETE_id_paroquia"), table_name="OBSERVACOES_LEMBRETE")
    op.drop_index(op.f("ix_OBSERVACOES_LEMBRETE_DATA_CADASTRO"), table_name="OBSERVACOES_LEMBRETE")
    op.drop_index(op.f("ix_OBSERVACOES_LEMBRETE_ATIVO"), table_name="OBSERVACOES_LEMBRETE")
    op.drop_table("OBSERVACOES_LEMBRETE")
