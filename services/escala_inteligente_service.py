from datetime import date
from models import Ministro, Escala, Missa, Indisponibilidade
from sqlalchemy import extract
import random


def selecionar_ministros(qtd, id_paroquia, missa):

    hoje = date.today()

    ministros = Ministro.query.filter_by(
        id_paroquia=id_paroquia
    ).all()

    ranking = []

    for ministro in ministros:

        # indisponibilidade
        indisponivel = Indisponibilidade.query.filter_by(
            id_ministro=ministro.id,
            data=missa.data,
            id_paroquia=id_paroquia
        ).first()

        if indisponivel:
            continue

        # conflito mesmo horário
        conflito = Escala.query.join(Missa).filter(
            Escala.id_ministro == ministro.id,
            Escala.id_paroquia == id_paroquia,
            Missa.data == missa.data,
            Missa.horario == missa.horario
        ).first()

        if conflito:
            continue

        # última missa
        ultima = Escala.query.join(Missa).filter(
            Escala.id_ministro == ministro.id,
            Escala.id_paroquia == id_paroquia
        ).order_by(Missa.data.desc()).first()

        if ultima and ultima.missa:
            dias_sem_servir = (hoje - ultima.missa.data).days
        else:
            dias_sem_servir = 60

        # total escalas
        total = Escala.query.filter_by(
            id_ministro=ministro.id,
            id_paroquia=id_paroquia
        ).count()

        # confirmações
        confirmadas = Escala.query.filter_by(
            id_ministro=ministro.id,
            confirmado=True,
            id_paroquia=id_paroquia
        ).count()

        confiabilidade = confirmadas / total if total else 1

        # escalas no mês
        escalas_mes = Escala.query.join(Missa).filter(
            Escala.id_ministro == ministro.id,
            Escala.id_paroquia == id_paroquia,
            extract("month", Missa.data) == missa.data.month,
            extract("year", Missa.data) == missa.data.year
        ).count()

        score = (
            dias_sem_servir * 2
            + confiabilidade * 15
            - escalas_mes * 4
        )

        ranking.append((ministro, score))

    # ordenar melhor score
    ranking.sort(key=lambda x: x[1], reverse=True)

    selecionados = []

    for ministro, score in ranking:

        selecionados.append(ministro)

        if len(selecionados) >= qtd:
            break

    return selecionados