#from flask import current_app
from datetime import datetime, timedelta
from models import Missa, Escala
from services.substituicao_automatica_service import verificar_substituicoes_automaticas

def enviar_lembretes_missa(app):

    with app.app_context():
        # 🔥 verificar substituições automáticas
        verificar_substituicoes_automaticas()

        agora = datetime.now()
        limite = agora + timedelta(hours=1)

        missas = Missa.query.filter(
            Missa.data == agora.date()
        ).all()

        for missa in missas:

            # restante do código
            pass