from models import Escala, db
import uuid

from services.notification_manager import NotificationManager


def salvar_escala(missa, ministros):

    # remove escala antiga
    Escala.query.filter_by(id_missa=missa.id).delete()

    escalados = []

    for ministro in ministros:

        nova = Escala(
            id_missa=missa.id,
            id_ministro=ministro.id,
            id_paroquia=missa.id_paroquia,
            token=str(uuid.uuid4())
        )

        db.session.add(nova)
        escalados.append(ministro)

    db.session.commit()

    # enviar notificações
    for ministro in escalados:

        try:

            NotificationManager.enviar(
                usuario_id=ministro.id,
                titulo="Nova escala",
                mensagem=f"Você foi escalado para {missa.data} às {missa.horario} na comunidade {missa.comunidade}.",
                url="/minhas-escalas"
            )

        except Exception:
            pass