from models import Disponibilidade, DisponibilidadeFixa, Indisponibilidade, IndisponibilidadeFixa


def semana_do_mes(data):
    return ((data.day - 1) // 7) + 1


def _score_regra_fixa(regra, semana_ref, horario_ref):
    if regra.dia_semana is None:
        return -1
    if regra.semana is not None and regra.semana != semana_ref:
        return -1
    if regra.horario is not None and regra.horario != horario_ref:
        return -1

    score = 10
    if regra.semana is not None:
        score += 4
    if regra.horario is not None:
        score += 2
    return score


def _score_regra_data(regra, horario_ref):
    if regra.horario is not None and regra.horario != horario_ref:
        return -1
    return 100 if regra.horario is not None else 90


def resolver_status_missa(ministro_id, missa, id_paroquia):
    semana_ref = semana_do_mes(missa.data)
    dia_semana = missa.data.weekday()

    indisponibilidades_fixas = IndisponibilidadeFixa.query.filter(
        IndisponibilidadeFixa.id_ministro == ministro_id,
        IndisponibilidadeFixa.id_paroquia == id_paroquia,
        IndisponibilidadeFixa.dia_semana == dia_semana,
    ).all()
    disponibilidades_fixas = DisponibilidadeFixa.query.filter(
        DisponibilidadeFixa.id_ministro == ministro_id,
        DisponibilidadeFixa.id_paroquia == id_paroquia,
        DisponibilidadeFixa.dia_semana == dia_semana,
    ).all()
    indisponibilidades_data = Indisponibilidade.query.filter(
        Indisponibilidade.id_ministro == ministro_id,
        Indisponibilidade.id_paroquia == id_paroquia,
        Indisponibilidade.data == missa.data,
    ).all()
    disponibilidades_data = Disponibilidade.query.filter(
        Disponibilidade.id_ministro == ministro_id,
        Disponibilidade.id_paroquia == id_paroquia,
        Disponibilidade.data == missa.data,
    ).all()

    melhor_indisponivel = max(
        (_score_regra_fixa(regra, semana_ref, missa.horario) for regra in indisponibilidades_fixas),
        default=-1,
    )
    melhor_disponivel = max(
        (_score_regra_fixa(regra, semana_ref, missa.horario) for regra in disponibilidades_fixas),
        default=-1,
    )

    melhor_indisponivel = max(
        melhor_indisponivel,
        max((_score_regra_data(regra, missa.horario) for regra in indisponibilidades_data), default=-1),
    )
    melhor_disponivel = max(
        melhor_disponivel,
        max((_score_regra_data(regra, missa.horario) for regra in disponibilidades_data), default=-1),
    )

    if melhor_indisponivel >= melhor_disponivel and melhor_indisponivel >= 0:
        return "indisponivel"
    if melhor_disponivel > melhor_indisponivel and melhor_disponivel >= 0:
        return "disponivel"
    return "neutro"


def listar_ministros_indisponiveis(ministro_ids, missa, id_paroquia):
    if not ministro_ids:
        return set()

    semana_ref = semana_do_mes(missa.data)
    dia_semana = missa.data.weekday()

    indisponibilidades_fixas = IndisponibilidadeFixa.query.filter(
        IndisponibilidadeFixa.id_ministro.in_(ministro_ids),
        IndisponibilidadeFixa.id_paroquia == id_paroquia,
        IndisponibilidadeFixa.dia_semana == dia_semana,
    ).all()
    disponibilidades_fixas = DisponibilidadeFixa.query.filter(
        DisponibilidadeFixa.id_ministro.in_(ministro_ids),
        DisponibilidadeFixa.id_paroquia == id_paroquia,
        DisponibilidadeFixa.dia_semana == dia_semana,
    ).all()
    indisponibilidades_data = Indisponibilidade.query.filter(
        Indisponibilidade.id_ministro.in_(ministro_ids),
        Indisponibilidade.id_paroquia == id_paroquia,
        Indisponibilidade.data == missa.data,
    ).all()
    disponibilidades_data = Disponibilidade.query.filter(
        Disponibilidade.id_ministro.in_(ministro_ids),
        Disponibilidade.id_paroquia == id_paroquia,
        Disponibilidade.data == missa.data,
    ).all()

    melhor_indisponivel = {ministro_id: -1 for ministro_id in ministro_ids}
    melhor_disponivel = {ministro_id: -1 for ministro_id in ministro_ids}

    for regra in indisponibilidades_fixas:
        score = _score_regra_fixa(regra, semana_ref, missa.horario)
        if score > melhor_indisponivel.get(regra.id_ministro, -1):
            melhor_indisponivel[regra.id_ministro] = score

    for regra in disponibilidades_fixas:
        score = _score_regra_fixa(regra, semana_ref, missa.horario)
        if score > melhor_disponivel.get(regra.id_ministro, -1):
            melhor_disponivel[regra.id_ministro] = score

    for regra in indisponibilidades_data:
        score = _score_regra_data(regra, missa.horario)
        if score > melhor_indisponivel.get(regra.id_ministro, -1):
            melhor_indisponivel[regra.id_ministro] = score

    for regra in disponibilidades_data:
        score = _score_regra_data(regra, missa.horario)
        if score > melhor_disponivel.get(regra.id_ministro, -1):
            melhor_disponivel[regra.id_ministro] = score

    return {
        ministro_id
        for ministro_id in ministro_ids
        if melhor_indisponivel.get(ministro_id, -1) >= melhor_disponivel.get(ministro_id, -1)
        and melhor_indisponivel.get(ministro_id, -1) >= 0
    }


def esta_indisponivel(ministro_id, missa, id_paroquia):
    return resolver_status_missa(ministro_id, missa, id_paroquia) == "indisponivel"

def esta_disponivel(ministro_id, missa, paroquia_id):

    # disponibilidade por data
    disp_data = Disponibilidade.query.filter_by(
        id_ministro=ministro_id,
        data=missa.data,
        id_paroquia=paroquia_id
    ).first()

    if disp_data:
        return True

    # disponibilidade fixa
    disp_fixa = DisponibilidadeFixa.query.filter_by(
        id_ministro=ministro_id,
        dia_semana=missa.data.weekday(),
        id_paroquia=paroquia_id
    ).first()

    if disp_fixa:
        return True

    return False

def pode_escalar(ministro_id, missa, paroquia_id):

    # 1️⃣ Se tem disponibilidade específica → PRIORIDADE MÁXIMA
    if esta_disponivel(ministro_id, missa, paroquia_id):
        return True

    # 2️⃣ Se está indisponível → NÃO pode
    if esta_indisponivel(ministro_id, missa, paroquia_id):
        return False

    # 3️⃣ Caso contrário → disponível por padrão
    return True
