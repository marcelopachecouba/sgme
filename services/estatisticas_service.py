from models import Escala, Ministro


def dados_confiabilidade(id_paroquia):
    ministros = Ministro.query.filter_by(id_paroquia=id_paroquia).all()

    dados = []
    for ministro in ministros:
        total = Escala.query.filter_by(
            id_ministro=ministro.id,
            id_paroquia=id_paroquia,
        ).count()
        confirmadas = Escala.query.filter_by(
            id_ministro=ministro.id,
            confirmado=True,
            id_paroquia=id_paroquia,
        ).count()
        pendentes = Escala.query.filter_by(
            id_ministro=ministro.id,
            confirmado=False,
            id_paroquia=id_paroquia,
        ).count()

        percentual = round((confirmadas / total) * 100) if total > 0 else 0

        dados.append({
            "ministro": ministro.nome,
            "total": total,
            "confirmadas": confirmadas,
            "pendentes": pendentes,
            "percentual": percentual,
        })

    return dados
