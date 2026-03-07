"""add periodo to missa

Revision ID: b7d2c4e8a1f0
Revises: f3a9b7c1d2e4
Create Date: 2026-03-07 01:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7d2c4e8a1f0"
down_revision = "f3a9b7c1d2e4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("missa", sa.Column("periodo", sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column("missa", "periodo")
