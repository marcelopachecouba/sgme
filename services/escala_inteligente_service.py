from datetime import timedelta
import random

from sqlalchemy import extract
from flask import current_app

from models import (
    Escala,
    Indisponibilidade,
    IndisponibilidadeFixa,
    Ministro,
    Missa,
)


def _cfg(key, default):
    try:
        return current_app.config.get(key, default)
    except RuntimeError:
        return default


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


def _tem_conflito_mesmo_horario(ministro_id, id_paroquia, missa):
    return Escala.query.join(Missa).filter(
        Escala.id_ministro == ministro_id,
        Escala.id_paroquia == id_paroquia,
        Missa.data == missa.data,
        Missa.horario == missa.horario,
    ).first() is not None


def _coletar_metricas(ministro_id, id_paroquia, missa):
    historico = Escala.query.join(Missa).filter(
        Escala.id_ministro == ministro_id,
        Escala.id_paroquia == id_paroquia,
        Missa.data < missa.data,
    )

    ultima_escala = historico.order_by(Missa.data.desc()).first()
    ultima_data = ultima_escala.missa.data if ultima_escala and ultima_escala.missa else None

    if ultima_data:
        dias_sem_servir = max((missa.data - ultima_data).days, 0)
    else:
        dias_sem_servir = 999

    total_historico = historico.count()
    confirmadas_historico = historico.filter(Escala.confirmado == True).count()

    confiabilidade = (
        confirmadas_historico / total_historico
        if total_historico
        else 1
    )

    janela_7 = int(_cfg("ESCALA_JANELA_7_DIAS", 7))
    janela_14 = int(_cfg("ESCALA_JANELA_14_DIAS", 14))

    inicio_7_dias = missa.data - timedelta(days=janela_7)
    inicio_14_dias = missa.data - timedelta(days=janela_14)

    escalas_7_dias = historico.filter(Missa.data >= inicio_7_dias).count()
    escalas_14_dias = historico.filter(Missa.data >= inicio_14_dias).count()

    escalas_mes = Escala.query.join(Missa).filter(
        Escala.id_ministro == ministro_id,
        Escala.id_paroquia == id_paroquia,
        extract("month", Missa.data) == missa.data.month,
        extract("year", Missa.data) == missa.data.year,
    ).count()

    return {
        "dias_sem_servir": dias_sem_servir,
        "confiabilidade": confiabilidade,
        "escalas_mes": escalas_mes,
        "escalas_7_dias": escalas_7_dias,
        "escalas_14_dias": escalas_14_dias,
        "total_historico": total_historico,
    }


def _calcular_score(metricas):
    limite_dias = int(_cfg("ESCALA_LIMITE_DIAS_SEM_SERVIR", 45))
    dias_peso = float(_cfg("ESCALA_SCORE_DIAS_SEM_SERVIR_PESO", 2.8))
    confiabilidade_peso = float(_cfg("ESCALA_SCORE_CONFIABILIDADE_PESO", 10))
    escalas_mes_peso = float(_cfg("ESCALA_SCORE_ESCALAS_MES_PESO", 5))
    escalas_7_peso = float(_cfg("ESCALA_SCORE_ESCALAS_7_DIAS_PESO", 12))
    escalas_14_peso = float(_cfg("ESCALA_SCORE_ESCALAS_14_DIAS_PESO", 4))
    historico_peso = float(_cfg("ESCALA_SCORE_TOTAL_HISTORICO_PESO", 0.15))

    dias_sem_servir = min(metricas["dias_sem_servir"], limite_dias)

    return (
        dias_sem_servir * dias_peso
        + metricas["confiabilidade"] * confiabilidade_peso
        - metricas["escalas_mes"] * escalas_mes_peso
        - metricas["escalas_7_dias"] * escalas_7_peso
        - metricas["escalas_14_dias"] * escalas_14_peso
        - metricas["total_historico"] * historico_peso
    )


def _candidato_restrito(metricas):
    restricao_dias_recentes = int(_cfg("ESCALA_RESTRICAO_DIAS_RECENTES", 3))
    restricao_max_7_dias = int(_cfg("ESCALA_RESTRICAO_MAX_7_DIAS", 2))

    return (
        metricas["dias_sem_servir"] < restricao_dias_recentes
        or metricas["escalas_7_dias"] >= restricao_max_7_dias
    )


def selecionar_ministros(qtd, id_paroquia, missa):
    ministros = Ministro.query.filter_by(id_paroquia=id_paroquia).all()

    priorizados = []
    restritos = []

    for ministro in ministros:
        if _esta_indisponivel(ministro.id, id_paroquia, missa):
            continue

        if _tem_conflito_mesmo_horario(ministro.id, id_paroquia, missa):
            continue

        metricas = _coletar_metricas(ministro.id, id_paroquia, missa)
        score = _calcular_score(metricas)
        item = (ministro, score)

        if _candidato_restrito(metricas):
            restritos.append(item)
        else:
            priorizados.append(item)

    random.shuffle(priorizados)
    random.shuffle(restritos)

    priorizados.sort(key=lambda x: x[1], reverse=True)
    restritos.sort(key=lambda x: x[1], reverse=True)

    selecionados = [m for m, _ in priorizados[:qtd]]

    if len(selecionados) < qtd:
        faltantes = qtd - len(selecionados)
        selecionados.extend([m for m, _ in restritos[:faltantes]])

    return selecionados
