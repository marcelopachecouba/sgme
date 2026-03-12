"""add location to reuniao_formacao

Revision ID: a4b5c6d7e8f9
Revises: f1c2d3e4b5a6
Create Date: 2026-03-12 00:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a4b5c6d7e8f9"
down_revision = "f1c2d3e4b5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reuniao_formacao", sa.Column("latitude", sa.String(length=50), nullable=True))
    op.add_column("reuniao_formacao", sa.Column("longitude", sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column("reuniao_formacao", "longitude")
    op.drop_column("reuniao_formacao", "latitude")
