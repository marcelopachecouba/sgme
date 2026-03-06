from models import (
    Ministro,
    Escala,
    Missa,
    Indisponibilidade,
    IndisponibilidadeFixa,
)
from sqlalchemy import extract
import random


def _esta_indisponivel(ministro_id, id_paroquia, missa):

    indisponibilidade = Indisponibilidade.query.filter(
        Indisponibilidade.id_ministro == ministro_id,
        Indisponibilidade.data == missa.data,
        Indisponibilidade.id_paroquia == id_paroquia,
        (Indisponibilidade.horario == None)
        | (Indisponibilidade.horario == missa.horario),
    ).first()

    if indisponibilidade:
        return True

    semana = (missa.data.day - 1) // 7 + 1
    dia_semana = missa.data.weekday()

    indisponibilidade_fixa = IndisponibilidadeFixa.query.filter(
        IndisponibilidadeFixa.id_ministro == ministro_id,
        IndisponibilidadeFixa.id_paroquia == id_paroquia,
        (IndisponibilidadeFixa.semana == semana)
        | (IndisponibilidadeFixa.semana == None),
        (IndisponibilidadeFixa.dia_semana == dia_semana)
        | (IndisponibilidadeFixa.dia_semana == None),
        (IndisponibilidadeFixa.horario == missa.horario)
        | (IndisponibilidadeFixa.horario == None),
    ).first()

    return indisponibilidade_fixa is not None


def selecionar_ministros(qtd, id_paroquia, missa):

    ministros = Ministro.query.filter_by(
        id_paroquia=id_paroquia
    ).all()

    ranking = []

    for ministro in ministros:

        if _esta_indisponivel(ministro.id, id_paroquia, missa):
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
            dias_sem_servir = (missa.data - ultima.missa.data).days
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
    random.shuffle(ranking)
    ranking.sort(key=lambda x: x[1], reverse=True)

    selecionados = []

    for ministro, score in ranking:

        selecionados.append(ministro)

        if len(selecionados) >= qtd:
            break

    return selecionados
