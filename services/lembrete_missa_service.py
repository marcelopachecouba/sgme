from flask import current_app
from datetime import datetime, timedelta
from models import Missa, Escala

def enviar_lembretes_missa():

    with current_app.app_context():

        agora = datetime.now()
        limite = agora + timedelta(hours=1)

        missas = Missa.query.filter(
            Missa.data == agora.date()
        ).all()

        for missa in missas:

            # restante do código
            pass