from models import Ministro, Escala, Missa, Indisponibilidade, db
from sqlalchemy import func
from datetime import date
from services.notificacao_service import notificar_escala_criada


def substituir_ministro(escala):

    missa = escala.missa
    paroquia = escala.id_paroquia

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)

    # busca todos ministros ativos
    ministros = Ministro.query.filter_by(
        id_paroquia=paroquia,
        pode_logar=True
    ).all()

    candidatos = []

    for ministro in ministros:

        # não escolher o mesmo que recusou
        if ministro.id == escala.id_ministro:
            continue

        # conflito de horário
        conflito = db.session.query(Escala)\
            .join(Missa)\
            .filter(
                Escala.id_ministro == ministro.id,
                Escala.id_paroquia == paroquia,
                Missa.data == missa.data,
                Missa.horario == missa.horario
            ).first()

        if conflito:
            continue

        # indisponibilidade
        indisponivel = Indisponibilidade.query.filter(
            Indisponibilidade.id_ministro == ministro.id,
            Indisponibilidade.id_paroquia == paroquia,
            Indisponibilidade.data == missa.data,
            (Indisponibilidade.horario == None)
            | (Indisponibilidade.horario == missa.horario),
        ).first()

        if indisponivel:
            continue

        # contar escalas no mês
        total_mes = db.session.query(func.count(Escala.id))\
            .join(Missa)\
            .filter(
                Escala.id_ministro == ministro.id,
                Escala.id_paroquia == paroquia,
                Missa.data >= inicio_mes
            ).scalar()

        candidatos.append({
            "ministro": ministro,
            "total": total_mes
        })

    if not candidatos:
        return False

    # ordenar por quem menos serviu
    candidatos.sort(key=lambda x: x["total"])

    escolhido = candidatos[0]["ministro"]

    nova = Escala(
        id_missa=missa.id,
        id_ministro=escolhido.id,
        id_paroquia=paroquia
    )

    db.session.add(nova)
    db.session.commit()

    # envia notificação
    notificar_escala_criada(escolhido, missa)

    return True
