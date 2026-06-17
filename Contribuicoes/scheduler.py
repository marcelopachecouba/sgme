import logging
from datetime import datetime

from extensions import db
from .services import verificar_contribuicoes_pendentes


logger = logging.getLogger(__name__)


def executar_verificacao_contribuicoes(app):
    with app.app_context():
        try:
            total = verificar_contribuicoes_pendentes()
            logger.info("Contribuicoes PIX verificadas em %s. confirmadas=%s", datetime.utcnow(), total)
        except Exception as exc:
            db.session.rollback()
            logger.error("Erro ao verificar contribuicoes PIX: %s", exc)


def registrar_agendamentos_contribuicoes(scheduler, app):
    scheduler.add_job(
        executar_verificacao_contribuicoes,
        trigger="interval",
        minutes=2,
        args=[app],
        max_instances=1,
        replace_existing=True,
        id="verificar_pix_contribuicoes",
    )
