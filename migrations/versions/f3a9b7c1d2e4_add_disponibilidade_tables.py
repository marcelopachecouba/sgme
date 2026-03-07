"""add disponibilidade and disponibilidade_fixa

Revision ID: f3a9b7c1d2e4
Revises: c9b8e4a1f2d3
Create Date: 2026-03-07 00:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f3a9b7c1d2e4"
down_revision = "c9b8e4a1f2d3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "disponibilidade",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_ministro", sa.Integer(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("horario", sa.String(length=10), nullable=True),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["id_ministro"], ["ministro.id"]),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "disponibilidade_fixa",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_ministro", sa.Integer(), nullable=False),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.Column("semana", sa.Integer(), nullable=True),
        sa.Column("dia_semana", sa.Integer(), nullable=True),
        sa.Column("horario", sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(["id_ministro"], ["ministro.id"]),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("disponibilidade_fixa")
    op.drop_table("disponibilidade")
