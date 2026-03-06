from datetime import date
from models import Ministro, Escala, Missa, Indisponibilidade, IndisponibilidadeFixa
import random
from sqlalchemy import extract


def calcular_score(ministro, id_paroquia):

    hoje = date.today()

    ultima = Escala.query.join(Missa).filter(
        Escala.id_ministro == ministro.id,
        Escala.id_paroquia == id_paroquia
    ).order_by(Missa.data.desc()).first()

    if ultima and ultima.missa:
        dias_sem_servir = (hoje - ultima.missa.data).days
    else:
        dias_sem_servir = 60

    total = Escala.query.filter_by(
        id_ministro=ministro.id,
        id_paroquia=id_paroquia
    ).count()

    confirmadas = Escala.query.filter_by(
        id_ministro=ministro.id,
        confirmado=True,
        id_paroquia=id_paroquia
    ).count()

    confiabilidade = confirmadas / total if total else 1

    escalas_mes = Escala.query.join(Missa).filter(
        Escala.id_ministro == ministro.id,
        Escala.id_paroquia == id_paroquia,
        extract("month", Missa.data) == hoje.month,
        extract("year", Missa.data) == hoje.year
    ).count()

    score = (
        dias_sem_servir * 2
        + confiabilidade * 15
        - escalas_mes * 4
    )

    return score


def selecionar_ministros(qtd, id_paroquia, missa):

    ministros = Ministro.query.filter_by(
        id_paroquia=id_paroquia
    ).all()

    random.shuffle(ministros)

    ranking = []

    semana = (missa.data.day - 1) // 7 + 1
    dia_semana = missa.data.weekday()

    for ministro in ministros:

        # 🔴 verifica indisponibilidade recorrente
        indisponivel = IndisponibilidadeFixa.query.filter(
            IndisponibilidadeFixa.id_ministro == ministro.id,
            (IndisponibilidadeFixa.semana == semana) |
            (IndisponibilidadeFixa.semana == None),
            IndisponibilidadeFixa.dia_semana == dia_semana,
            IndisponibilidadeFixa.horario == missa.horario
        ).first()

        if indisponivel:
            continue

        score = calcular_score(ministro, id_paroquia)

        ranking.append((ministro, score))

    ranking.sort(key=lambda x: x[1], reverse=True)

    selecionados = []

    for ministro, score in ranking:

        selecionados.append(ministro)

        if len(selecionados) >= qtd:
            break

    return selecionados