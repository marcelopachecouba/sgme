from datetime import datetime, timedelta

from models import Escala, Missa
from services.firebase_service import enviar_push


def enviar_lembretes(app=None):
    if app is not None:
        with app.app_context():
            _processar_lembretes()
        return

    _processar_lembretes()


def _processar_lembretes():
    agora = datetime.now()
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

        if not (agora <= horario_missa <= limite):
            continue

        escalas = Escala.query.filter_by(id_missa=missa.id).all()
        for escala in escalas:
            ministro = escala.ministro
            if ministro and ministro.firebase_token:
                enviar_push(
                    ministro.firebase_token,
                    "Lembrete de Escala",
                    f"Voce tem escala hoje as {missa.horario} - {missa.comunidade}"
                )
