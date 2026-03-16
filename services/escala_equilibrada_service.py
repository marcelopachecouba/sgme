import uuid
from sqlalchemy import extract
from models import db, Missa, Escala, Ministro
from services.disponibilidade_service import esta_indisponivel


def gerar_escala_equilibrada_mes(mes, ano, paroquia_id, casais_juntos=True):

    missas = Missa.query.filter(
        Missa.id_paroquia == paroquia_id,
        extract("month", Missa.data) == mes,
        extract("year", Missa.data) == ano
    ).all()

    ministros = Ministro.query.filter_by(
        id_paroquia=paroquia_id
    ).all()

    contagem = {m.id: 0 for m in ministros}

    for missa in missas:

        candidatos = []

        for ministro in ministros:

            if esta_indisponivel(ministro.id, missa, paroquia_id):
                continue

            candidatos.append(ministro)

        candidatos.sort(key=lambda m: contagem[m.id])

        selecionados = candidatos[:missa.qtd_ministros]

        for ministro in selecionados:

            nova = Escala(
                id_missa=missa.id,
                id_ministro=ministro.id,
                id_paroquia=paroquia_id,
                token=str(uuid.uuid4())
            )

            db.session.add(nova)

            contagem[ministro.id] += 1

    db.session.commit()

def semana_do_mes(data):
    return ((data.day - 1) // 7) + 1


def copiar_escala_mes(mes_base, ano_base, mes_novo, ano_novo, paroquia_id):

    from sqlalchemy import extract
    from models import Missa, Escala
    from services.disponibilidade_service import esta_indisponivel
    import uuid

    missas_base = Missa.query.filter(
        Missa.id_paroquia == paroquia_id,
        extract("month", Missa.data) == mes_base,
        extract("year", Missa.data) == ano_base
    ).all()

    missas_novas = Missa.query.filter(
        Missa.id_paroquia == paroquia_id,
        extract("month", Missa.data) == mes_novo,
        extract("year", Missa.data) == ano_novo
    ).all()

    for missa_base in missas_base:

        semana = semana_do_mes(missa_base.data)

        # ignorar 5ª semana
        if semana == 5:
            continue

        dia_semana = missa_base.data.weekday()

        missa_destino = None

        for missa in missas_novas:

            if (
                semana_do_mes(missa.data) == semana
                and missa.data.weekday() == dia_semana
                and missa.horario == missa_base.horario
                and missa.comunidade == missa_base.comunidade
            ):
                missa_destino = missa
                break

        if not missa_destino:
            continue

        escalas_base = Escala.query.filter_by(
            id_missa=missa_base.id
        ).all()

        contador = 0

        for escala in escalas_base:

            if contador >= missa_destino.qtd_ministros:
                break

            ministro = escala.ministro

            if esta_indisponivel(ministro.id, missa_destino, paroquia_id):
                continue

            existe = Escala.query.filter_by(
                id_missa=missa_destino.id,
                id_ministro=ministro.id
            ).first()

            if existe:
                continue

            nova = Escala(
                id_missa=missa_destino.id,
                id_ministro=ministro.id,
                id_paroquia=paroquia_id,
                token=str(uuid.uuid4())
            )

            db.session.add(nova)

            contador += 1

    db.session.commit()