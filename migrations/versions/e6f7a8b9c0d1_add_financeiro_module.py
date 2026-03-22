"""add financeiro module

Revision ID: e6f7a8b9c0d1
Revises: d1f2e3a4b5c6
Create Date: 2026-03-22 12:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e6f7a8b9c0d1"
down_revision = "d1f2e3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contas_correntes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("saldo_atual", sa.Numeric(12, 2), nullable=False),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_contas_correntes_id_paroquia"), "contas_correntes", ["id_paroquia"], unique=False)

    op.create_table(
        "centros_custo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_centros_custo_id_paroquia"), "centros_custo", ["id_paroquia"], unique=False)

    op.create_table(
        "categorias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_categorias_id_paroquia"), "categorias", ["id_paroquia"], unique=False)

    op.create_table(
        "duplicatas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("descricao", sa.String(length=255), nullable=False),
        sa.Column("valor_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantidade_parcelas", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_duplicatas_id_paroquia"), "duplicatas", ["id_paroquia"], unique=False)
    op.create_index(op.f("ix_duplicatas_tipo"), "duplicatas", ["tipo"], unique=False)

    op.create_table(
        "subcategorias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("categoria_id", sa.Integer(), nullable=False),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subcategorias_categoria_id"), "subcategorias", ["categoria_id"], unique=False)
    op.create_index(op.f("ix_subcategorias_id_paroquia"), "subcategorias", ["id_paroquia"], unique=False)

    op.create_table(
        "duplicatas_parcelas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("duplicata_id", sa.Integer(), nullable=False),
        sa.Column("numero_parcela", sa.Integer(), nullable=False),
        sa.Column("data_vencimento", sa.Date(), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["duplicata_id"], ["duplicatas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("duplicata_id", "numero_parcela", name="uq_duplicata_numero_parcela"),
    )
    op.create_index(op.f("ix_duplicatas_parcelas_data_vencimento"), "duplicatas_parcelas", ["data_vencimento"], unique=False)
    op.create_index(op.f("ix_duplicatas_parcelas_duplicata_id"), "duplicatas_parcelas", ["duplicata_id"], unique=False)
    op.create_index(op.f("ix_duplicatas_parcelas_id_paroquia"), "duplicatas_parcelas", ["id_paroquia"], unique=False)
    op.create_index(op.f("ix_duplicatas_parcelas_status"), "duplicatas_parcelas", ["status"], unique=False)

    op.create_table(
        "extrato_importado",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("descricao", sa.String(length=255), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("conta_corrente_id", sa.Integer(), nullable=False),
        sa.Column("lancamento_financeiro_id", sa.Integer(), nullable=True),
        sa.Column("conciliado", sa.String(length=5), nullable=False),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["conta_corrente_id"], ["contas_correntes.id"]),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_extrato_importado_conciliado"), "extrato_importado", ["conciliado"], unique=False)
    op.create_index(op.f("ix_extrato_importado_conta_corrente_id"), "extrato_importado", ["conta_corrente_id"], unique=False)
    op.create_index(op.f("ix_extrato_importado_data"), "extrato_importado", ["data"], unique=False)
    op.create_index(op.f("ix_extrato_importado_id_paroquia"), "extrato_importado", ["id_paroquia"], unique=False)
    op.create_index(op.f("ix_extrato_importado_lancamento_financeiro_id"), "extrato_importado", ["lancamento_financeiro_id"], unique=False)

    op.create_table(
        "extrato_padrao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("descricao_padrao", sa.String(length=255), nullable=False),
        sa.Column("categoria_id", sa.Integer(), nullable=False),
        sa.Column("subcategoria_id", sa.Integer(), nullable=True),
        sa.Column("centro_custo_id", sa.Integer(), nullable=False),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"]),
        sa.ForeignKeyConstraint(["centro_custo_id"], ["centros_custo.id"]),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.ForeignKeyConstraint(["subcategoria_id"], ["subcategorias.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_extrato_padrao_categoria_id"), "extrato_padrao", ["categoria_id"], unique=False)
    op.create_index(op.f("ix_extrato_padrao_centro_custo_id"), "extrato_padrao", ["centro_custo_id"], unique=False)
    op.create_index(op.f("ix_extrato_padrao_id_paroquia"), "extrato_padrao", ["id_paroquia"], unique=False)
    op.create_index(op.f("ix_extrato_padrao_subcategoria_id"), "extrato_padrao", ["subcategoria_id"], unique=False)

    op.create_table(
        "lancamentos_financeiros",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("descricao", sa.String(length=255), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("conta_corrente_id", sa.Integer(), nullable=False),
        sa.Column("categoria_id", sa.Integer(), nullable=False),
        sa.Column("subcategoria_id", sa.Integer(), nullable=True),
        sa.Column("centro_custo_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("origem", sa.String(length=20), nullable=False),
        sa.Column("duplicata_parcela_id", sa.Integer(), nullable=True),
        sa.Column("id_paroquia", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"]),
        sa.ForeignKeyConstraint(["centro_custo_id"], ["centros_custo.id"]),
        sa.ForeignKeyConstraint(["conta_corrente_id"], ["contas_correntes.id"]),
        sa.ForeignKeyConstraint(["duplicata_parcela_id"], ["duplicatas_parcelas.id"]),
        sa.ForeignKeyConstraint(["id_paroquia"], ["paroquia.id"]),
        sa.ForeignKeyConstraint(["subcategoria_id"], ["subcategorias.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lancamentos_financeiros_categoria_id"), "lancamentos_financeiros", ["categoria_id"], unique=False)
    op.create_index(op.f("ix_lancamentos_financeiros_centro_custo_id"), "lancamentos_financeiros", ["centro_custo_id"], unique=False)
    op.create_index(op.f("ix_lancamentos_financeiros_conta_corrente_id"), "lancamentos_financeiros", ["conta_corrente_id"], unique=False)
    op.create_index(op.f("ix_lancamentos_financeiros_data"), "lancamentos_financeiros", ["data"], unique=False)
    op.create_index(op.f("ix_lancamentos_financeiros_duplicata_parcela_id"), "lancamentos_financeiros", ["duplicata_parcela_id"], unique=False)
    op.create_index(op.f("ix_lancamentos_financeiros_id_paroquia"), "lancamentos_financeiros", ["id_paroquia"], unique=False)
    op.create_index(op.f("ix_lancamentos_financeiros_origem"), "lancamentos_financeiros", ["origem"], unique=False)
    op.create_index(op.f("ix_lancamentos_financeiros_status"), "lancamentos_financeiros", ["status"], unique=False)
    op.create_index(op.f("ix_lancamentos_financeiros_subcategoria_id"), "lancamentos_financeiros", ["subcategoria_id"], unique=False)
    op.create_index(op.f("ix_lancamentos_financeiros_tipo"), "lancamentos_financeiros", ["tipo"], unique=False)
    op.create_foreign_key(
        "fk_extrato_importado_lancamento_financeiro_id",
        "extrato_importado",
        "lancamentos_financeiros",
        ["lancamento_financeiro_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_extrato_importado_lancamento_financeiro_id", "extrato_importado", type_="foreignkey")
    op.drop_index(op.f("ix_lancamentos_financeiros_tipo"), table_name="lancamentos_financeiros")
    op.drop_index(op.f("ix_lancamentos_financeiros_subcategoria_id"), table_name="lancamentos_financeiros")
    op.drop_index(op.f("ix_lancamentos_financeiros_status"), table_name="lancamentos_financeiros")
    op.drop_index(op.f("ix_lancamentos_financeiros_origem"), table_name="lancamentos_financeiros")
    op.drop_index(op.f("ix_lancamentos_financeiros_id_paroquia"), table_name="lancamentos_financeiros")
    op.drop_index(op.f("ix_lancamentos_financeiros_duplicata_parcela_id"), table_name="lancamentos_financeiros")
    op.drop_index(op.f("ix_lancamentos_financeiros_data"), table_name="lancamentos_financeiros")
    op.drop_index(op.f("ix_lancamentos_financeiros_conta_corrente_id"), table_name="lancamentos_financeiros")
    op.drop_index(op.f("ix_lancamentos_financeiros_centro_custo_id"), table_name="lancamentos_financeiros")
    op.drop_index(op.f("ix_lancamentos_financeiros_categoria_id"), table_name="lancamentos_financeiros")
    op.drop_table("lancamentos_financeiros")

    op.drop_index(op.f("ix_extrato_padrao_subcategoria_id"), table_name="extrato_padrao")
    op.drop_index(op.f("ix_extrato_padrao_id_paroquia"), table_name="extrato_padrao")
    op.drop_index(op.f("ix_extrato_padrao_centro_custo_id"), table_name="extrato_padrao")
    op.drop_index(op.f("ix_extrato_padrao_categoria_id"), table_name="extrato_padrao")
    op.drop_table("extrato_padrao")

    op.drop_index(op.f("ix_extrato_importado_id_paroquia"), table_name="extrato_importado")
    op.drop_index(op.f("ix_extrato_importado_data"), table_name="extrato_importado")
    op.drop_index(op.f("ix_extrato_importado_conta_corrente_id"), table_name="extrato_importado")
    op.drop_index(op.f("ix_extrato_importado_conciliado"), table_name="extrato_importado")
    op.drop_index(op.f("ix_extrato_importado_lancamento_financeiro_id"), table_name="extrato_importado")
    op.drop_table("extrato_importado")

    op.drop_index(op.f("ix_duplicatas_parcelas_status"), table_name="duplicatas_parcelas")
    op.drop_index(op.f("ix_duplicatas_parcelas_id_paroquia"), table_name="duplicatas_parcelas")
    op.drop_index(op.f("ix_duplicatas_parcelas_duplicata_id"), table_name="duplicatas_parcelas")
    op.drop_index(op.f("ix_duplicatas_parcelas_data_vencimento"), table_name="duplicatas_parcelas")
    op.drop_table("duplicatas_parcelas")

    op.drop_index(op.f("ix_subcategorias_id_paroquia"), table_name="subcategorias")
    op.drop_index(op.f("ix_subcategorias_categoria_id"), table_name="subcategorias")
    op.drop_table("subcategorias")

    op.drop_index(op.f("ix_duplicatas_tipo"), table_name="duplicatas")
    op.drop_index(op.f("ix_duplicatas_id_paroquia"), table_name="duplicatas")
    op.drop_table("duplicatas")

    op.drop_index(op.f("ix_categorias_id_paroquia"), table_name="categorias")
    op.drop_table("categorias")

    op.drop_index(op.f("ix_centros_custo_id_paroquia"), table_name="centros_custo")
    op.drop_table("centros_custo")

    op.drop_index(op.f("ix_contas_correntes_id_paroquia"), table_name="contas_correntes")
    op.drop_table("contas_correntes")
