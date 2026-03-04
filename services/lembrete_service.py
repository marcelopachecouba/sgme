ffrom datetime import datetime, timedelta
from flask import current_app

from models import Missa, Escala
from services.firebase_service import enviar_push


def enviar_lembretes():

    # abre contexto do Flask (necessário para SQLAlchemy)
    with current_app.app_context():

        agora = datetime.now()

        # verifica missas nas próximas 2 horas
        limite = agora + timedelta(hours=2)

        missas = Missa.query.filter(
            Missa.data >= agora.date(),
            Missa.data <= limite.date()
        ).all()

        for missa in missas:

            horario_missa = datetime.combine(
                missa.data,
                datetime.strptime(missa.horario, "%H:%M").time()
            )

            if agora <= horario_missa <= limite:

                escalas = Escala.query.filter_by(
                    id_missa=missa.id
                ).all()

                for escala in escalas:

                    ministro = escala.ministro

                    if ministro and ministro.firebase_token:

                        enviar_push(
                            ministro.firebase_token,
                            "Lembrete de Escala",
                            f"Você tem escala hoje às {missa.horario} - {missa.comunidade}"
                        )