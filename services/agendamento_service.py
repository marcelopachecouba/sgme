import logging

from services.lembrete_missa_service import enviar_lembretes_missa
from services.notification_manager import NotificationManager
from services.whatsapp_service import enviar_lembretes_whatsapp

from rifas.services import cancelar_pagamentos_expirados
from extensions import db
from datetime import datetime


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

# 🔥 👉 FALTA ISSO AQUI
    scheduler.add_job(
        executar_expiracao_rifas,
        trigger="interval",
        minutes=60,
        args=[app],
        max_instances=1,
        replace_existing=True,
        misfire_grace_time=60,
        id="expirar_rifas",
    )

    scheduler.start()

def executar_expiracao_rifas(app):
    with app.app_context():
        logger.info("JOB RIFA INICIADO")
        logger.info("JOB RIFA FINALIZADO")
        try:
            cancelar_pagamentos_expirados()
            db.session.commit()

            logger.info("Expiração de rifas concluída com sucesso")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao expirar rifas: {str(e)}")
