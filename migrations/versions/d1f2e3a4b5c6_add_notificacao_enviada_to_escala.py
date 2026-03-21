"""add notificacao enviada to escala

Revision ID: d1f2e3a4b5c6
Revises: a83be55d76e1
Create Date: 2026-03-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d1f2e3a4b5c6"
down_revision = "a83be55d76e1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "escala",
        sa.Column("notificacao_enviada", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(op.f("ix_escala_notificacao_enviada"), "escala", ["notificacao_enviada"], unique=False)
    op.alter_column("escala", "notificacao_enviada", server_default=None)


def downgrade():
    op.drop_index(op.f("ix_escala_notificacao_enviada"), table_name="escala")
    op.drop_column("escala", "notificacao_enviada")
