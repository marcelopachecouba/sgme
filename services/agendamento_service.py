import logging

from services.lembrete_missa_service import enviar_lembretes_missa
from services.notification_manager import NotificationManager
from services.whatsapp_service import enviar_lembretes_whatsapp


logger = logging.getLogger(__name__)


def executar_lembretes_whatsapp_agendados(app):
    with app.app_context():
        resultado = enviar_lembretes_whatsapp()
        logger.info(
            "Job WhatsApp concluido. data_alvo=%s enviados=%s ministros_sem_telefone=%s falhas=%s",
            resultado["data_alvo"],
            resultado["enviados"],
            resultado["ministros_sem_telefone"],
            resultado["falhas"],
        )


def registrar_agendamentos(scheduler, app):
    if scheduler.running:
        return

    scheduler.add_job(
        enviar_lembretes_missa,
        trigger="interval",
        minutes=10,
        args=[app],
        max_instances=1,
        replace_existing=True,
        id="lembretes_missa",
    )

    scheduler.add_job(
        executar_lembretes_whatsapp_agendados,
        trigger="cron",
        hour=18,
        minute=0,
        args=[app],
        max_instances=1,
        replace_existing=True,
        id="lembretes_whatsapp_amanha",
    )

    scheduler.add_job(
        NotificationManager.limpar_tokens_inativos,
        trigger="interval",
        hours=24,
        id="limpar_tokens_push",
    )

    scheduler.start()
