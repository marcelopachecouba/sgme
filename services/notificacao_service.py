import logging

from services.firebase_service import enviar_push
from services.whatsapp_service import gerar_link_whatsapp


logger = logging.getLogger(__name__)


def notificar_escala_criada(ministro, missa):
    if ministro.firebase_token:
        enviar_push(
            ministro.firebase_token,
            "Nova Escala",
            f"Voce foi escalado para {missa.data.strftime('%d/%m')} as {missa.horario}",
        )

    return gerar_link_whatsapp(ministro, missa)


def notificar_escala_removida(ministro, missa):
    data = missa.data.strftime("%d/%m/%Y")

    titulo = "Escala Alterada"
    mensagem = (
        "Voce foi removido da escala.\n"
        f"Data: {data}\n"
        f"Horario: {missa.horario}\n"
        f"Comunidade: {missa.comunidade}"
    )

    if ministro.firebase_token:
        enviar_push(ministro.firebase_token, titulo, mensagem)

    link = gerar_link_whatsapp(ministro, missa)
    logger.info("Link WhatsApp remocao gerado para ministro_id=%s", getattr(ministro, "id", None))
    return link


def notificar_confirmacao(admin, ministro, missa):
    if not admin.firebase_token:
        return

    data = missa.data.strftime("%d/%m/%Y")
    titulo = "Presenca Confirmada"
    mensagem = (
        f"{ministro.nome} confirmou presenca.\n"
        f"Data: {data}\n"
        f"Horario: {missa.horario}"
    )

    enviar_push(admin.firebase_token, titulo, mensagem)
