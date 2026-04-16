from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from extensions import db
from rifas.services import cancelar_pagamentos_expirados

def job_expirar_pagamentos():
    print(f"[{datetime.utcnow()}] Rodando expiração de pagamentos...")

    try:
        cancelar_pagamentos_expirados()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("Erro no job:", str(e))

def start_scheduler(app):
    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        func=job_expirar_pagamentos,
        trigger="interval",
        minutes=5  # 🔥 roda a cada 5 minutos
    )

    scheduler.start()

    print("Scheduler iniciado com sucesso")