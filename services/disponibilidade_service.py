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


def esta_indisponivel(ministro_id, missa, paroquia_id):

    from models import Disponibilidade

    data = missa.data
    dia_semana = data.weekday()

    # 1️⃣ DISPONIBILIDADE POR DATA (tem prioridade)
    disp_data = Disponibilidade.query.filter_by(
        id_ministro=ministro_id,
        data=data,
        tipo="disponivel",
        id_paroquia=paroquia_id
    ).first()

    if disp_data:
        return False

    # 2️⃣ INDISPONIBILIDADE POR DATA
    indis_data = Disponibilidade.query.filter_by(
        id_ministro=ministro_id,
        data=data,
        tipo="indisponivel",
        id_paroquia=paroquia_id
    ).first()

    if indis_data:
        return True

    # 3️⃣ INDISPONIBILIDADE SEMANAL
    indis_semana = Disponibilidade.query.filter_by(
        id_ministro=ministro_id,
        dia_semana=dia_semana,
        tipo="indisponivel",
        id_paroquia=paroquia_id
    ).first()

    if indis_semana:
        return True

    return False