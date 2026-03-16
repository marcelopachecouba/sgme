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