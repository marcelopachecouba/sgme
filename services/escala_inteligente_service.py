from collections import defaultdict
from datetime import timedelta
import random

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import extract, or_

from models import (
    CasalMinisterio,
    Disponibilidade,
    DisponibilidadeFixa,
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


def _calcular_score(metricas):
    limite_dias = int(_cfg("ESCALA_LIMITE_DIAS_SEM_SERVIR", 45))
    dias_peso = float(_cfg("ESCALA_SCORE_DIAS_SEM_SERVIR_PESO", 2.8))
    confiabilidade_peso = float(_cfg("ESCALA_SCORE_CONFIABILIDADE_PESO", 10))
    escalas_mes_peso = float(_cfg("ESCALA_SCORE_ESCALAS_MES_PESO", 5))
    escalas_7_peso = float(_cfg("ESCALA_SCORE_ESCALAS_7_DIAS_PESO", 12))
    escalas_14_peso = float(_cfg("ESCALA_SCORE_ESCALAS_14_DIAS_PESO", 4))
    historico_peso = float(_cfg("ESCALA_SCORE_TOTAL_HISTORICO_PESO", 0.15))
    disponibilidade_peso = float(_cfg("ESCALA_SCORE_DISPONIBILIDADE_PESO", 8))

    dias_sem_servir = min(metricas["dias_sem_servir"], limite_dias)

    return (
        dias_sem_servir * dias_peso
        + metricas["confiabilidade"] * confiabilidade_peso
        - metricas["escalas_mes"] * escalas_mes_peso
        - metricas["escalas_7_dias"] * escalas_7_peso
        - metricas["escalas_14_dias"] * escalas_14_peso
        - metricas["total_historico"] * historico_peso
        + metricas["disponivel_preferencial"] * disponibilidade_peso
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


def _fracao_casal_preferida(domingo):
    # Mantem preferencia por casais, sem monopolizar a escala.
    if domingo:
        return float(_cfg("ESCALA_CASAL_FRACAO_DOMINGO", 0.5))
    return float(_cfg("ESCALA_CASAL_FRACAO_SEMANA", 0.4))


def _tolerancia_balanceamento_mensal():
    # 0 = estrito (sempre prioriza menor qtd no mes), 1 = permite pequena folga.
    return max(0, int(_cfg("ESCALA_BALANCEAMENTO_MENSAL_TOLERANCIA", 0)))


def _meta_mensal_por_ministro():
    # Objetivo operacional: preencher 1 escala para todos, depois +1 (ex.: 2), e assim por rodadas.
    return max(1, int(_cfg("ESCALA_META_MENSAL_POR_MINISTRO", 2)))


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

    try:
        disponibilidade_pontual = {
            row[0]
            for row in Disponibilidade.query.with_entities(Disponibilidade.id_ministro).filter(
                Disponibilidade.id_paroquia == id_paroquia,
                Disponibilidade.id_ministro.in_(ministro_ids),
                Disponibilidade.data == missa.data,
                or_(Disponibilidade.horario == None, Disponibilidade.horario == missa.horario),
            ).all()
        }
    except SQLAlchemyError:
        disponibilidade_pontual = set()

    try:
        disponibilidade_fixa = {
            row[0]
            for row in DisponibilidadeFixa.query.with_entities(DisponibilidadeFixa.id_ministro).filter(
                DisponibilidadeFixa.id_paroquia == id_paroquia,
                DisponibilidadeFixa.id_ministro.in_(ministro_ids),
                or_(DisponibilidadeFixa.semana == semana, DisponibilidadeFixa.semana == None),
                or_(DisponibilidadeFixa.dia_semana == dia_semana, DisponibilidadeFixa.dia_semana == None),
                or_(DisponibilidadeFixa.horario == missa.horario, DisponibilidadeFixa.horario == None),
            ).all()
        }
    except SQLAlchemyError:
        disponibilidade_fixa = set()

    disponibilidade_preferencial = disponibilidade_pontual.union(disponibilidade_fixa)

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
    escalas_7_map = {}

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
            "disponivel_preferencial": 1 if ministro_id in disponibilidade_preferencial else 0,
        }

        score = _calcular_score(metricas)
        score_map[ministro_id] = score
        escalas_7_map[ministro_id] = metricas["escalas_7_dias"]
        item = {
            "ministro": ministro,
            "score": score,
            "escalas_mes": metricas["escalas_mes"],
            "disponivel_preferencial": metricas["disponivel_preferencial"],
        }

        if _candidato_restrito(metricas):
            restritos.append(item)
        else:
            priorizados.append(item)

    random.shuffle(priorizados)
    random.shuffle(restritos)
    # Prioridade de ordenacao:
    # 1) disponibilidade declarada
    # 2) equilibrio mensal
    # 3) score inteligente
    priorizados.sort(key=lambda x: (-x["disponivel_preferencial"], x["escalas_mes"], -x["score"]))
    restritos.sort(key=lambda x: (-x["disponivel_preferencial"], x["escalas_mes"], -x["score"]))

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

    # Balanceamento mensal forte por rodadas:
    # primeiro todos com 0, depois todos com 1, depois todos com 2...
    if candidatos_ordenados:
        menor_qtd_mes = min(escalas_mes_map.get(m.id, 0) for m in candidatos_ordenados)
        meta_mensal = _meta_mensal_por_ministro()
        tolerancia = _tolerancia_balanceamento_mensal()

        if menor_qtd_mes < meta_mensal:
            limite_rodada = menor_qtd_mes + tolerancia
        else:
            # Apos atingir a meta base, continua em rodadas (N, N+1, ...).
            limite_rodada = menor_qtd_mes

        faixa_prioritaria = [
            m for m in candidatos_ordenados
            if escalas_mes_map.get(m.id, 0) <= limite_rodada
        ]
        faixa_restante = [
            m for m in candidatos_ordenados
            if escalas_mes_map.get(m.id, 0) > limite_rodada
        ]
        candidatos_ordenados = faixa_prioritaria + faixa_restante

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
            "qtd_max_mes": max(escalas_mes_map.get(a.id, 0), escalas_mes_map.get(b.id, 0)),
            "qtd_mes": escalas_mes_map.get(a.id, 0) + escalas_mes_map.get(b.id, 0),
            "qtd_domingo_mes": escalas_domingo_mes_map.get(a.id, 0) + escalas_domingo_mes_map.get(b.id, 0),
            "qtd_7_dias": escalas_7_map.get(a.id, 0) + escalas_7_map.get(b.id, 0),
            "score": score_map.get(a.id, 0) + score_map.get(b.id, 0),
            "disp_par": int(
                a.id in disponibilidade_preferencial and b.id in disponibilidade_preferencial
            ),
        })
        ids_em_par.add(a.id)
        ids_em_par.add(b.id)

    if domingo:
        par_entries.sort(
            key=lambda x: (-x["disp_par"], x["qtd_domingo_mes"], x["qtd_max_mes"], x["qtd_mes"], -x["score"])
        )
    else:
        # Na semana, prioriza casal disponivel e que serviu menos recentemente.
        par_entries.sort(key=lambda x: (-x["disp_par"], x["qtd_7_dias"], x["qtd_max_mes"], x["qtd_mes"], -x["score"]))

    # Singles incluem todos os candidatos (inclusive quem tem casal),
    # para nao bloquear o preenchimento justo quando o parceiro estiver indisponivel.
    singles_ordenados = list(candidatos_ordenados)

    selecionados = []
    selecionados_ids = set()

    # Etapa 1: prioridade absoluta para quem declarou disponibilidade
    # (pontual ou fixa), respeitando limite de vagas da missa.
    disponiveis_ordenados = [
        m for m in candidatos_ordenados
        if m.id in disponibilidade_preferencial
    ]

    if disponiveis_ordenados:
        disp_por_id = {m.id: m for m in disponiveis_ordenados}
        pares_disp = []
        usados_disp = set()

        for ministro in disponiveis_ordenados:
            if ministro.id in usados_disp:
                continue
            parceiro_id = casal_map.get(ministro.id)
            parceiro = disp_por_id.get(parceiro_id) if parceiro_id else None
            if not parceiro or parceiro.id in usados_disp:
                continue

            a, b = (ministro, parceiro) if ministro.id < parceiro.id else (parceiro, ministro)
            if a.id in usados_disp or b.id in usados_disp:
                continue

            pares_disp.append((a, b))
            usados_disp.add(a.id)
            usados_disp.add(b.id)

        # Casais disponiveis entram primeiro.
        for a, b in pares_disp:
            if len(selecionados) + 2 > qtd:
                break
            if a.id in selecionados_ids or b.id in selecionados_ids:
                continue
            selecionados.append(a)
            selecionados.append(b)
            selecionados_ids.add(a.id)
            selecionados_ids.add(b.id)

        # Depois, completa com disponiveis restantes (inclusive casados sem parceiro disponivel).
        for ministro in disponiveis_ordenados:
            if len(selecionados) >= qtd:
                break
            if ministro.id in selecionados_ids:
                continue
            selecionados.append(ministro)
            selecionados_ids.add(ministro.id)

    if len(selecionados) >= qtd:
        return selecionados[:qtd]

    # Balanceamento mensal estrito: tenta preencher com quem esta na menor quantidade no mes.
    # So amplia o teto (0->1->2...) se nao houver candidatos suficientes.
    if candidatos_ordenados:
        menor_qtd_mes = min(escalas_mes_map.get(m.id, 0) for m in candidatos_ordenados)
        maior_qtd_mes = max(escalas_mes_map.get(m.id, 0) for m in candidatos_ordenados)
    else:
        menor_qtd_mes = 0
        maior_qtd_mes = 0

    fracao_casal = max(0.0, min(1.0, _fracao_casal_preferida(domingo)))
    meta_slots_casal = int(round(qtd * fracao_casal))
    meta_pares_base = min(len(par_entries), meta_slots_casal // 2)
    if domingo and meta_pares_base == 0 and len(par_entries) > 0 and qtd >= 2:
        meta_pares_base = 1

    teto_mes = menor_qtd_mes
    teto_limite = maior_qtd_mes + qtd

    while len(selecionados) < qtd and teto_mes <= teto_limite:
        progresso = False
        vagas = qtd - len(selecionados)
        pares_escolhidos = 0

        # Casais entram antes da etapa individual (domingo e semana).
        meta_pares = min(meta_pares_base, vagas // 2)
        if not domingo and meta_pares == 0 and len(par_entries) > 0 and qtd >= 2:
            # Na semana, garante ao menos uma tentativa de par quando houver casais elegiveis.
            meta_pares = 1
        for par in par_entries:
            if pares_escolhidos >= meta_pares:
                break
            if len(selecionados) + 2 > qtd:
                break
            if par["a"].id in selecionados_ids or par["b"].id in selecionados_ids:
                continue
            if escalas_mes_map.get(par["a"].id, 0) > teto_mes or escalas_mes_map.get(par["b"].id, 0) > teto_mes:
                continue
            selecionados.append(par["a"])
            selecionados.append(par["b"])
            selecionados_ids.add(par["a"].id)
            selecionados_ids.add(par["b"].id)
            pares_escolhidos += 1
            progresso = True

        for ministro in singles_ordenados:
            if len(selecionados) >= qtd:
                break
            if ministro.id in selecionados_ids:
                continue
            if escalas_mes_map.get(ministro.id, 0) > teto_mes:
                continue
            if domingo:
                # No domingo, evita escalar apenas um membro do casal
                # quando o parceiro tambem esta elegivel.
                parceiro_id = casal_map.get(ministro.id)
                parceiro = candidatos_por_id.get(parceiro_id) if parceiro_id else None
                if parceiro and parceiro.id not in selecionados_ids:
                    continue
            selecionados.append(ministro)
            selecionados_ids.add(ministro.id)
            progresso = True

        # Se faltar vaga, tenta mais casais mantendo teto.
        for par in par_entries:
            if len(selecionados) >= qtd:
                break
            if len(selecionados) + 2 > qtd:
                continue
            if par["a"].id in selecionados_ids or par["b"].id in selecionados_ids:
                continue
            if escalas_mes_map.get(par["a"].id, 0) > teto_mes or escalas_mes_map.get(par["b"].id, 0) > teto_mes:
                continue
            selecionados.append(par["a"])
            selecionados.append(par["b"])
            selecionados_ids.add(par["a"].id)
            selecionados_ids.add(par["b"].id)
            progresso = True

        if not progresso:
            teto_mes += 1

    if domingo and len(selecionados) < qtd:
        # Fallback final para evitar deixar vagas abertas quando nao ha
        # combinacao possivel apenas com casais.
        for ministro in singles_ordenados:
            if len(selecionados) >= qtd:
                break
            if ministro.id in selecionados_ids:
                continue
            selecionados.append(ministro)
            selecionados_ids.add(ministro.id)

    return selecionados
