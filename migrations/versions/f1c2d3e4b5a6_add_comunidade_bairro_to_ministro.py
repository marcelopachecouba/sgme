"""add comunidade_bairro to ministro

Revision ID: f1c2d3e4b5a6
Revises: d6634527d3df
Create Date: 2026-03-11 19:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f1c2d3e4b5a6"
down_revision = "d6634527d3df"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ministro", sa.Column("comunidade_bairro", sa.String(length=120), nullable=True))


def downgrade():
    op.drop_column("ministro", "comunidade_bairro")
