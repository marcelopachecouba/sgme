from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from extensions import db
from rifas.services import (
    cancelar_pagamentos_expirados,
    lembrar_comprovante,
    verificar_pagamentos_pendentes  # 🔥 NOVO
)


def job_expirar_pagamentos(app):
    with app.app_context():
        print(f"[{datetime.utcnow()}] Expirando pagamentos...")
        try:
            cancelar_pagamentos_expirados()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("Erro expiração:", str(e))


def job_lembrete(app):
    with app.app_context():
        print(f"[{datetime.utcnow()}] Enviando lembretes...")
        try:
            lembrar_comprovante()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("Erro lembrete:", str(e))


def job_verificar_pix(app):
    with app.app_context():
        print(f"[{datetime.utcnow()}] Verificando PIX pendentes...")
        try:
            verificar_pagamentos_pendentes()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("Erro verificação PIX:", str(e))


def start_scheduler(app):
    scheduler = BackgroundScheduler(timezone="UTC")

    # 🔥 expiração
    scheduler.add_job(
        func=job_expirar_pagamentos,
        args=[app],
        trigger="interval",
        minutes=60
    )

    # 🔥 lembrete comprovante
    scheduler.add_job(
        func=job_lembrete,
        args=[app],
        trigger="interval",
        minutes=10
    )

    # 🔥 NOVO: reconciliação PIX
    scheduler.add_job(
        func=job_verificar_pix,
        args=[app],
        trigger="interval",
        minutes=2
    )

    scheduler.start()

    print("🚀 Scheduler iniciado com sucesso")