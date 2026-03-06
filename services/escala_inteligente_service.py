from collections import defaultdict
from datetime import timedelta
import random

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import extract, or_

from models import CasalMinisterio, Escala, Indisponibilidade, IndisponibilidadeFixa, Ministro, Missa


def _cfg(key, default):
    try:
        return current_app.config.get(key, default)
    except RuntimeError:
        return default


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


def _obter_pares_casal(id_paroquia):
    """
    Formato em config:
    ESCALA_CASAL_PARES="12:34,56:78"
    """
    pares = {}

    try:
        casais_db = CasalMinisterio.query.filter_by(
            id_paroquia=id_paroquia,
            ativo=True
        ).all()
        for casal in casais_db:
            a = int(casal.id_ministro_1)
            b = int(casal.id_ministro_2)
            if a <= 0 or b <= 0 or a == b:
                continue
            pares[a] = b
            pares[b] = a
    except SQLAlchemyError:
        pass

    bruto = (_cfg("ESCALA_CASAL_PARES", "") or "").strip()
    blocos = [b.strip() for b in bruto.replace(";", ",").split(",") if b.strip()]

    for bloco in blocos:
        if ":" not in bloco:
            continue

        a_str, b_str = bloco.split(":", 1)
        try:
            a = int(a_str.strip())
            b = int(b_str.strip())
        except ValueError:
            continue

        if a <= 0 or b <= 0 or a == b:
            continue

        if a not in pares:
            pares[a] = b
        if b not in pares:
            pares[b] = a

    return pares


def selecionar_ministros(qtd, id_paroquia, missa, considerar_periodos_anteriores=True):
    ministros = Ministro.query.filter_by(id_paroquia=id_paroquia).all()
    if not ministros or qtd <= 0:
        return []

    ministro_ids = [m.id for m in ministros]
    ids_set = set(ministro_ids)

    semana = (missa.data.day - 1) // 7 + 1
    dia_semana = missa.data.weekday()
    janela_7 = int(_cfg("ESCALA_JANELA_7_DIAS", 7))
    janela_14 = int(_cfg("ESCALA_JANELA_14_DIAS", 14))
    inicio_7 = missa.data - timedelta(days=janela_7)
    inicio_14 = missa.data - timedelta(days=janela_14)

    # Bloqueia repeticao no mesmo dia, mesmo em horarios diferentes.
    conflito_ids = {
        row[0]
        for row in Escala.query.join(Missa).with_entities(Escala.id_ministro).filter(
            Escala.id_paroquia == id_paroquia,
            Escala.id_ministro.in_(ministro_ids),
            Missa.data == missa.data,
        ).all()
    }

    indisponivel_pontual = {
        row[0]
        for row in Indisponibilidade.query.with_entities(Indisponibilidade.id_ministro).filter(
            Indisponibilidade.id_paroquia == id_paroquia,
            Indisponibilidade.id_ministro.in_(ministro_ids),
            Indisponibilidade.data == missa.data,
            or_(Indisponibilidade.horario == None, Indisponibilidade.horario == missa.horario),
        ).all()
    }

    indisponivel_fixo = {
        row[0]
        for row in IndisponibilidadeFixa.query.with_entities(IndisponibilidadeFixa.id_ministro).filter(
            IndisponibilidadeFixa.id_paroquia == id_paroquia,
            IndisponibilidadeFixa.id_ministro.in_(ministro_ids),
            or_(IndisponibilidadeFixa.semana == semana, IndisponibilidadeFixa.semana == None),
            or_(IndisponibilidadeFixa.dia_semana == dia_semana, IndisponibilidadeFixa.dia_semana == None),
            or_(IndisponibilidadeFixa.horario == missa.horario, IndisponibilidadeFixa.horario == None),
        ).all()
    }

    indisponiveis = indisponivel_pontual.union(indisponivel_fixo)

    historico_query = Escala.query.join(Missa).with_entities(
        Escala.id_ministro,
        Escala.confirmado,
        Missa.data,
    ).filter(
        Escala.id_paroquia == id_paroquia,
        Escala.id_ministro.in_(ministro_ids),
        Missa.data < missa.data,
    )

    if not considerar_periodos_anteriores:
        historico_query = historico_query.filter(
            extract("month", Missa.data) == missa.data.month,
            extract("year", Missa.data) == missa.data.year,
        )

    historico_rows = historico_query.all()

    hist_por_ministro = defaultdict(list)
    for ministro_id, confirmado, data in historico_rows:
        hist_por_ministro[ministro_id].append((data, confirmado))

    escalas_mes_rows = Escala.query.join(Missa).with_entities(
        Escala.id_ministro,
        Escala.id,
    ).filter(
        Escala.id_paroquia == id_paroquia,
        Escala.id_ministro.in_(ministro_ids),
        extract("month", Missa.data) == missa.data.month,
        extract("year", Missa.data) == missa.data.year,
    ).all()

    escalas_mes_map = defaultdict(int)
    for ministro_id, _ in escalas_mes_rows:
        escalas_mes_map[ministro_id] += 1

    escalas_domingo_mes_rows = Escala.query.join(Missa).with_entities(
        Escala.id_ministro,
        Escala.id,
    ).filter(
        Escala.id_paroquia == id_paroquia,
        Escala.id_ministro.in_(ministro_ids),
        extract("month", Missa.data) == missa.data.month,
        extract("year", Missa.data) == missa.data.year,
        extract("dow", Missa.data) == 0,
    ).all()

    escalas_domingo_mes_map = defaultdict(int)
    for ministro_id, _ in escalas_domingo_mes_rows:
        escalas_domingo_mes_map[ministro_id] += 1

    priorizados = []
    restritos = []
    score_map = {}

    for ministro in ministros:
        ministro_id = ministro.id
        if ministro_id not in ids_set:
            continue
        if ministro_id in conflito_ids:
            continue
        if ministro_id in indisponiveis:
            continue

        hist = hist_por_ministro.get(ministro_id, [])
        total_historico = len(hist)
        confirmadas_historico = sum(1 for _, conf in hist if conf is True)
        confiabilidade = (confirmadas_historico / total_historico) if total_historico else 1

        if hist:
            ultima_data = max(data for data, _ in hist)
            dias_sem_servir = max((missa.data - ultima_data).days, 0)
            escalas_7_dias = sum(1 for data, _ in hist if data >= inicio_7)
            escalas_14_dias = sum(1 for data, _ in hist if data >= inicio_14)
        else:
            dias_sem_servir = 999
            escalas_7_dias = 0
            escalas_14_dias = 0

        metricas = {
            "dias_sem_servir": dias_sem_servir,
            "confiabilidade": confiabilidade,
            "escalas_mes": escalas_mes_map.get(ministro_id, 0),
            "escalas_7_dias": escalas_7_dias,
            "escalas_14_dias": escalas_14_dias,
            "total_historico": total_historico,
        }

        score = _calcular_score(metricas)
        score_map[ministro_id] = score
        item = {
            "ministro": ministro,
            "score": score,
            "escalas_mes": metricas["escalas_mes"],
        }

        if _candidato_restrito(metricas):
            restritos.append(item)
        else:
            priorizados.append(item)

    random.shuffle(priorizados)
    random.shuffle(restritos)
    # Equilibrio mensal vem primeiro: menos escalas no mes tem prioridade.
    # Em empate no mes, usa score inteligente.
    priorizados.sort(key=lambda x: (x["escalas_mes"], -x["score"]))
    restritos.sort(key=lambda x: (x["escalas_mes"], -x["score"]))

    domingo = missa.data.weekday() == 6
    casal_map = _obter_pares_casal(id_paroquia)

    candidatos_ordenados = [x["ministro"] for x in priorizados] + [x["ministro"] for x in restritos]
    candidatos_por_id = {m.id: m for m in candidatos_ordenados}

    if domingo and candidatos_ordenados:
        menor_qtd_domingo = min(
            escalas_domingo_mes_map.get(m.id, 0) for m in candidatos_ordenados
        )
        nao_repetidos_domingo = [
            m for m in candidatos_ordenados
            if escalas_domingo_mes_map.get(m.id, 0) == menor_qtd_domingo
        ]
        repetidos_domingo = [
            m for m in candidatos_ordenados
            if escalas_domingo_mes_map.get(m.id, 0) > menor_qtd_domingo
        ]
        candidatos_ordenados = nao_repetidos_domingo + repetidos_domingo

    # Prioriza casal como unidade quando ambos estao elegiveis.
    par_entries = []
    ids_em_par = set()

    for ministro in candidatos_ordenados:
        if ministro.id in ids_em_par:
            continue
        parceiro_id = casal_map.get(ministro.id)
        parceiro = candidatos_por_id.get(parceiro_id) if parceiro_id else None
        if not parceiro or parceiro.id in ids_em_par:
            continue

        a, b = (ministro, parceiro) if ministro.id < parceiro.id else (parceiro, ministro)
        if a.id in ids_em_par or b.id in ids_em_par:
            continue

        par_entries.append({
            "a": a,
            "b": b,
            "qtd_mes": escalas_mes_map.get(a.id, 0) + escalas_mes_map.get(b.id, 0),
            "qtd_domingo_mes": escalas_domingo_mes_map.get(a.id, 0) + escalas_domingo_mes_map.get(b.id, 0),
            "score": score_map.get(a.id, 0) + score_map.get(b.id, 0),
        })
        ids_em_par.add(a.id)
        ids_em_par.add(b.id)

    if domingo:
        par_entries.sort(key=lambda x: (x["qtd_domingo_mes"], x["qtd_mes"], -x["score"]))
    else:
        par_entries.sort(key=lambda x: (x["qtd_mes"], -x["score"]))

    selecionados = []
    selecionados_ids = set()

    # Primeiro tenta encaixar casais completos.
    for par in par_entries:
        if len(selecionados) + 2 > qtd:
            continue
        if par["a"].id in selecionados_ids or par["b"].id in selecionados_ids:
            continue
        selecionados.append(par["a"])
        selecionados.append(par["b"])
        selecionados_ids.add(par["a"].id)
        selecionados_ids.add(par["b"].id)
        if len(selecionados) >= qtd:
            break

    # Depois completa com candidatos individuais.
    for ministro in candidatos_ordenados:
        if len(selecionados) >= qtd:
            break
        if ministro.id in selecionados_ids:
            continue

        parceiro_id = casal_map.get(ministro.id)
        parceiro = candidatos_por_id.get(parceiro_id) if parceiro_id else None

        if parceiro and parceiro.id not in selecionados_ids and len(selecionados) + 2 <= qtd:
            selecionados.append(ministro)
            selecionados.append(parceiro)
            selecionados_ids.add(ministro.id)
            selecionados_ids.add(parceiro.id)
            continue

        selecionados.append(ministro)
        selecionados_ids.add(ministro.id)

    return selecionados
