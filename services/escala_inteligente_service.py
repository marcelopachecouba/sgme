from datetime import date
from models import Ministro, Escala, Missa


def calcular_score(ministro):

    hoje = date.today()

    ultima = Escala.query\
        .filter_by(id_ministro=ministro.id)\
        .order_by(Escala.id.desc())\
        .first()

    if ultima and ultima.missa:
        dias_sem_servir = (hoje - ultima.missa.data).days
    else:
        dias_sem_servir = 30

    total = Escala.query.filter_by(id_ministro=ministro.id).count()

    confirmadas = Escala.query\
        .filter_by(id_ministro=ministro.id, confirmado=True)\
        .count()

    confiabilidade = confirmadas / total if total else 1

    escalas_mes = Escala.query.join(Missa)\
        .filter(
            Escala.id_ministro == ministro.id,
            Missa.data.month == hoje.month
        ).count()

    score = (
        dias_sem_servir * 2
        + confiabilidade * 10
        - escalas_mes * 3
    )

    return score


def selecionar_ministros(qtd, id_paroquia):

    ministros = Ministro.query.filter_by(
        id_paroquia=id_paroquia
    ).all()

    ranking = []

    for m in ministros:
        ranking.append((m, calcular_score(m)))

    ranking.sort(key=lambda x: x[1], reverse=True)

    selecionados = [r[0] for r in ranking[:qtd]]

    return selecionados