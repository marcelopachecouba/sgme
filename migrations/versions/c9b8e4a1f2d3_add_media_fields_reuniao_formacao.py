"""add media fields to reuniao_formacao

Revision ID: c9b8e4a1f2d3
Revises: 2f4a6c1b9d10
Create Date: 2026-03-07 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9b8e4a1f2d3"
down_revision = "2f4a6c1b9d10"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reuniao_formacao", sa.Column("foto_url", sa.String(length=300), nullable=True))
    op.add_column("reuniao_formacao", sa.Column("video_url", sa.String(length=300), nullable=True))
    op.add_column("reuniao_formacao", sa.Column("video_arquivo_url", sa.String(length=300), nullable=True))


def downgrade():
    op.drop_column("reuniao_formacao", "video_arquivo_url")
    op.drop_column("reuniao_formacao", "video_url")
    op.drop_column("reuniao_formacao", "foto_url")
