"""add presenca reuniao formacao

Revision ID: 2f4a6c1b9d10
Revises: 00ea8bed83f1
Create Date: 2026-03-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2f4a6c1b9d10"
down_revision = "00ea8bed83f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reuniao_formacao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("assunto", sa.String(length=200), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reuniao_formacao_data"),
        "reuniao_formacao",
        ["data"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reuniao_formacao_id_paroquia"),
        "reuniao_formacao",
        ["id_paroquia"],
        unique=False,
    )

    op.create_table(
        "presenca_reuniao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_reuniao", sa.Integer(), nullable=False),
        sa.Column("id_ministro", sa.Integer(), nullable=False),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.Column("presente", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["id_ministro"], ["ministro.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.ForeignKeyConstraint(["id_reuniao"], ["reuniao_formacao.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_reuniao", "id_ministro", name="uq_presenca_reuniao_ministro"),
    )
    op.create_index(
        op.f("ix_presenca_reuniao_id_ministro"),
        "presenca_reuniao",
        ["id_ministro"],
        unique=False,
    )
    op.create_index(
        op.f("ix_presenca_reuniao_id_paroquia"),
        "presenca_reuniao",
        ["id_paroquia"],
        unique=False,
    )
    op.create_index(
        op.f("ix_presenca_reuniao_id_reuniao"),
        "presenca_reuniao",
        ["id_reuniao"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_presenca_reuniao_id_reuniao"), table_name="presenca_reuniao")
    op.drop_index(op.f("ix_presenca_reuniao_id_paroquia"), table_name="presenca_reuniao")
    op.drop_index(op.f("ix_presenca_reuniao_id_ministro"), table_name="presenca_reuniao")
    op.drop_table("presenca_reuniao")

    op.drop_index(op.f("ix_reuniao_formacao_id_paroquia"), table_name="reuniao_formacao")
    op.drop_index(op.f("ix_reuniao_formacao_data"), table_name="reuniao_formacao")
    op.drop_table("reuniao_formacao")
