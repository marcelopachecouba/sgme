def upgrade():
    op.add_column(
        'vendedores',
        sa.Column('telefone', sa.String(length=20), nullable=True)
    )


def downgrade():
    op.drop_column('vendedores', 'telefone')