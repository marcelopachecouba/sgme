"""initial schema

Revision ID: 0f1e2d3c4b5a
Revises:
Create Date: 2026-03-31 16:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0f1e2d3c4b5a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paroquia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ministro",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=True),
        sa.Column("telefone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=120), nullable=True),
        sa.Column("data_nascimento", sa.Date(), nullable=True),
        sa.Column("tempo_ministerio", sa.Integer(), nullable=True),
        sa.Column("data_cadastro", sa.Date(), nullable=True),
        sa.Column("id_paroquia", sa.Integer(), nullable=True),
        sa.Column("token_publico", sa.String(length=120), nullable=True),
        sa.Column("cpf", sa.String(length=14), nullable=True),
        sa.Column("comunidade", sa.String(length=30), nullable=True),
        sa.Column("senha_hash", sa.String(length=200), nullable=True),
        sa.Column("pode_logar", sa.Boolean(), nullable=True),
        sa.Column("tipo", sa.String(length=20), nullable=True),
        sa.Column("primeiro_acesso", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="ministro_email_key"),
        sa.UniqueConstraint("nome", "id_paroquia", name="unique_ministro_paroquia"),
        sa.UniqueConstraint("token_publico", name="ministro_token_publico_key"),
    )
    op.create_index("idx_ministro_paroquia", "ministro", ["id_paroquia"], unique=False)

    op.create_table(
        "missa",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("horario", sa.String(length=10), nullable=True),
        sa.Column("comunidade", sa.String(length=100), nullable=True),
        sa.Column("qtd_ministros", sa.Integer(), nullable=True),
        sa.Column("id_paroquia", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_missa_data", "missa", ["data"], unique=False)

    op.create_table(
        "escala",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_missa", sa.Integer(), nullable=True),
        sa.Column("id_ministro", sa.Integer(), nullable=True),
        sa.Column("confirmado", sa.Boolean(), nullable=True),
        sa.Column("presente", sa.Boolean(), nullable=True),
        sa.Column("id_paroquia", sa.Integer(), nullable=True),
        sa.Column("token", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["id_missa"], ["missa.id"]),
        sa.ForeignKeyConstraint(["id_ministro"], ["ministro.id"]),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="escala_token_key"),
    )
    op.create_index("idx_escala_missa", "escala", ["id_missa"], unique=False)
    op.create_index("idx_escala_ministro", "escala", ["id_ministro"], unique=False)

    op.create_table(
        "escala_fixa",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("semana", sa.Integer(), nullable=True),
        sa.Column("dia_semana", sa.Integer(), nullable=True),
        sa.Column("horario", sa.String(length=10), nullable=True),
        sa.Column("comunidade", sa.String(length=100), nullable=True),
        sa.Column("id_ministro", sa.Integer(), nullable=True),
        sa.Column("id_paroquia", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["id_ministro"], ["ministro.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "indisponibilidade",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_ministro", sa.Integer(), nullable=True),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("horario", sa.String(length=10), nullable=True),
        sa.Column("id_paroquia", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["id_ministro"], ["ministro.id"]),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("indisponibilidade")
    op.drop_table("escala_fixa")
    op.drop_index("idx_escala_ministro", table_name="escala")
    op.drop_index("idx_escala_missa", table_name="escala")
    op.drop_table("escala")
    op.drop_index("idx_missa_data", table_name="missa")
    op.drop_table("missa")
    op.drop_index("idx_ministro_paroquia", table_name="ministro")
    op.drop_table("ministro")
    op.drop_table("paroquia")
