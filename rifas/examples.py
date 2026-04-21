from extensions import db
from rifas.services import create_team, create_vendor, generate_vendor_link


def criar_exemplo_equipe_vendedor() -> dict:
    """Exemplo simples de bootstrap para equipe e vendedor."""
    equipe = create_team(nome="Equipe Centro", ativa=True)
    vendedor = create_vendor(nome="Joao Silva", codigo="JOAO123", equipe_id=equipe.id)
    db.session.commit()

    return {
        "equipe_id": equipe.id,
        "equipe_nome": equipe.nome,
        "vendedor_id": vendedor.id,
        "vendedor_codigo": vendedor.codigo,
        "link_vendedor": generate_vendor_link(vendedor.codigo),
    }
