from datetime import datetime, timedelta

from models import Escala, Missa, db
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

        try:

            horario_missa = datetime.combine(
                missa.data,
                datetime.strptime(missa.horario, "%H:%M").time()
            )

        except Exception:
            continue

        if not (agora <= horario_missa <= limite):
            continue

        escalas = Escala.query.filter_by(
            id_missa=missa.id
        ).all()

        for escala in escalas:

            ministro = escala.ministro

            if not ministro:
                continue

            if not ministro.firebase_token:
                continue

            # evita duplicar notificação
            if getattr(escala, "lembrete_enviado", False):
                continue

            try:

                enviar_push(
                    ministro.firebase_token,
                    "Lembrete de Escala",
                    f"Você tem escala hoje às {missa.horario} - {missa.comunidade}",
                    data={
                        "url": "/minhas-escalas"
                    }
                )

                escala.lembrete_enviado = True

            except Exception:
                print("Erro ao enviar push")

    db.session.commit()