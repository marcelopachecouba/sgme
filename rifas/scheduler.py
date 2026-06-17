from contribuicoes.services import verificar_contribuicoes_pendentes
from ofertas.routes import importar_pix_automatico
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

    scheduler.add_job(
        func=job_importar_ofertas,
        args=[app],
        trigger="cron",
        hour="6,12,18,21",
        minute=0,
        id="importacao_ofertas"
    )

    #scheduler.add_job(
        #func=job_verificar_contribuicoes,
        #args=[app],
        #trigger="interval",
        #minutes=1,
        #id="contribuicoes_pix",
        #replace_existing=True,
    #)


    scheduler.add_job(
        verificar_contribuicoes_pendentes,
        "interval",
        minutes=60,
        id="contribuicoes_pix",
        replace_existing=True
    )    

    scheduler.start()

    print("🚀 Scheduler iniciado com sucesso")

def job_importar_ofertas(app):

    with app.app_context():

        print(
            f"[{datetime.utcnow()}] Importando PIX das ofertas..."
        )

        try:

            importar_pix_automatico()

            db.session.commit()

        except Exception as e:

            db.session.rollback()

            print(
                "Erro importação ofertas:",
                str(e)
            )

def job_verificar_contribuicoes(app):

    with app.app_context():

        print(
            f"[{datetime.utcnow()}] Verificando contribuições..."
        )

        try:

            verificar_contribuicoes_pendentes()

            db.session.commit()

        except Exception as e:

            db.session.rollback()

            print(
                "Erro contribuições:",
                str(e)
            )