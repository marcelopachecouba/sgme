import os

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, send_from_directory
from flask_migrate import Migrate

from config import Config
from extensions import db, login_manager
from models import Ministro
from mural.mural_routes import mural_bp
from routes.admin_routes import admin_bp
from routes.api_routes import api_bp
from routes.auth_routes import auth_bp
from routes.avisos_routes import avisos_bp
from routes.busca_routes import busca_bp
from routes.casais_routes import casais_bp
from routes.dashboard_routes import dashboard_bp
from routes.escala_routes import escala_bp
from routes.estatisticas_routes import estatisticas_bp
from routes.indisponibilidade_routes import indisp_bp
from routes.minhas_escalas_routes import minhas_escalas_bp
from routes.ministros_routes import ministros_bp
from routes.missas_routes import missas_bp
from routes.presencas_routes import presencas_bp
from routes.publico_routes import publico_bp
from routes.superadmin_routes import superadmin_bp
from services.firebase_service import iniciar_firebase
from services.lembrete_missa_service import enviar_lembretes_missa


scheduler = BackgroundScheduler()
migrate = Migrate()


def _registrar_blueprints(app):
    blueprints = [
        auth_bp,
        dashboard_bp,
        ministros_bp,
        missas_bp,
        escala_bp,
        estatisticas_bp,
        publico_bp,
        admin_bp,
        avisos_bp,
        indisp_bp,
        casais_bp,
        presencas_bp,
        mural_bp,
        busca_bp,
        api_bp,
        superadmin_bp,
        minhas_escalas_bp,
    ]

    for blueprint in blueprints:
        app.register_blueprint(blueprint)


def _registrar_rotas_internas(app):
    @app.route("/health")
    def health():
        return "ok"

    @app.route("/firebase-messaging-sw.js")
    def firebase_sw():
        return send_from_directory("static", "firebase-messaging-sw.js")

    @app.context_processor
    def variaveis_globais():
        return {"proxima": None}


def _configurar_login():
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Ministro, int(user_id))


def _iniciar_scheduler(app):
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
    scheduler.start()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    _configurar_login()

    iniciar_firebase()
    _registrar_rotas_internas(app)
    _registrar_blueprints(app)

    if app.config.get("ENV") == "development" or os.getenv("FLASK_ENV") == "development":
        _iniciar_scheduler(app)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
