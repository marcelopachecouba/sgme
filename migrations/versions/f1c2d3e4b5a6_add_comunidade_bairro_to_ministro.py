"""add comunidade_bairro to ministro

Revision ID: f1c2d3e4b5a6
Revises: b7d2c4e8a1f0
Create Date: 2026-03-11 19:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f1c2d3e4b5a6"
down_revision = "b7d2c4e8a1f0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ministro", sa.Column("comunidade_bairro", sa.String(length=120), nullable=True))


def downgrade():
    op.drop_column("ministro", "comunidade_bairro")
