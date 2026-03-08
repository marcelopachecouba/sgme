from datetime import datetime, timedelta
from models import Missa, Escala
from services.firebase_service import enviar_push
from flask import current_app
from sqlalchemy import and_

def enviar_lembretes_missa():

    agora = datetime.now()
    limite = agora + timedelta(hours=1)

    missas = Missa.query.filter(
        Missa.data == agora.date()
    ).all()

    for missa in missas:

        hora_missa = datetime.combine(missa.data, datetime.strptime(missa.horario, "%H:%M").time())

        if agora <= hora_missa <= limite:

            escalas = Escala.query.filter_by(id_missa=missa.id).all()

            for escala in escalas:

                ministro = escala.ministro

                if ministro and ministro.firebase_token:

                    enviar_push(
                        ministro.firebase_token,
                        "Lembrete de Missa",
                        f"Você está escalado hoje às {missa.horario} na {missa.comunidade}"
                    )