from datetime import datetime, timedelta

from models import PedidoSubstituicao, Escala, db
from services.pedido_substituicao_service import _elegiveis_para_substituicao
from services.firebase_service import enviar_push
from services.notificacao_service import notificar_escala_criada


def verificar_substituicoes_automaticas():

    limite = datetime.utcnow() - timedelta(minutes=10)

    pedidos = PedidoSubstituicao.query.filter(
        PedidoSubstituicao.status == "aberto",
        PedidoSubstituicao.criado_em <= limite
    ).all()

    for pedido in pedidos:

        escala = db.session.get(Escala, pedido.id_escala)

        if not escala:
            pedido.status = "cancelado"
            continue

        # verifica elegíveis
        candidatos = _elegiveis_para_substituicao(escala)

        if not candidatos:
            continue

        substituto = candidatos[0]

        # aplica substituição
        escala.id_ministro = substituto.id
        escala.confirmado = False
        escala.presente = False

        pedido.status = "automatico"
        pedido.id_ministro_aceite = substituto.id
        pedido.respondido_em = datetime.utcnow()

        # commit
        db.session.commit()

        # push
        if substituto.firebase_token:

            enviar_push(
                substituto.firebase_token,
                "Substituição automática",
                f"Você foi escalado automaticamente para "
                f"{escala.missa.data.strftime('%d/%m')} "
                f"às {escala.missa.horario}"
            )

        # notificação interna
        notificar_escala_criada(substituto, escala.missa)