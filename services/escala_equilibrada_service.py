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

    for missa_base in missas_base:

        nova_data = missa_base.data.replace(month=mes_novo, year=ano_novo)

        nova_missa = Missa.query.filter_by(
            data=nova_data,
            horario=missa_base.horario,
            id_paroquia=paroquia_id
        ).first()

        if not nova_missa:
            continue

        escalas_base = Escala.query.filter_by(
            id_missa=missa_base.id
        ).all()

        for escala in escalas_base:

            ministro = escala.ministro

            if esta_indisponivel(ministro.id, nova_missa, paroquia_id):
                continue

            nova = Escala(
                id_missa=nova_missa.id,
                id_ministro=ministro.id,
                id_paroquia=paroquia_id,
                token=str(uuid.uuid4())
            )

            db.session.add(nova)

    db.session.commit()