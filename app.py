import os
import cloudinary
from dotenv import load_dotenv

load_dotenv()

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, send_from_directory
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix

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
from financeiro import financeiro_bp, init_financeiro_dash
from rifas.routes_admin import rifas_admin_bp
from rifas.routes_public import rifas_public_bp
from routes.indisponibilidade_routes import indisp_bp
from routes.minhas_escalas_routes import minhas_escalas_bp
from routes.ministros_routes import ministros_bp
from routes.missas_routes import missas_bp
from routes.presencas_routes import presencas_bp
from routes.publico_routes import publico_bp
from routes.superadmin_routes import superadmin_bp
from services.firebase_service import iniciar_firebase
from services.agendamento_service import registrar_agendamentos
from routes.push_routes import push_bp
from routes.notificacoes_routes import notificacao_bp
from routes.observacoes_lembrete_routes import observacoes_lembrete_bp
from datetime import timedelta


scheduler = BackgroundScheduler(timezone=Config.SCHEDULER_TIMEZONE)
migrate = Migrate()


def _registrar_blueprints(app):
    blueprints = [
        auth_bp,
        dashboard_bp,
        ministros_bp,
        missas_bp,
        escala_bp,
        estatisticas_bp,
        financeiro_bp,
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
        push_bp,
        notificacao_bp,
        observacoes_lembrete_bp,
        rifas_public_bp,
        rifas_admin_bp,
    ]

    for blueprint in blueprints:
        app.register_blueprint(blueprint)


cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)


def _registrar_rotas_internas(app):
    @app.route("/health")
    def health():
        return "ok"

    @app.route("/firebase-messaging-sw.js")
    def firebase_sw():
        response = send_from_directory("static", "firebase-messaging-sw.js")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.context_processor
    def variaveis_globais():
        return {"proxima": None}


def _configurar_login():
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Ministro, int(user_id))


def _iniciar_scheduler(app):
    registrar_agendamentos(scheduler, app)

        
def create_app(config_override=None):
    app = Flask(__name__)
    app.config.from_object(Config)

    @app.template_filter('telefone')
    def telefone_filter(tel):
        tel = ''.join(filter(str.isdigit, tel or ''))
        if len(tel) == 11:
            return f"({tel[:2]}) {tel[2:7]}-{tel[7:]}"
        elif len(tel) == 10:
            return f"({tel[:2]}) {tel[2:6]}-{tel[6:]}"
        return tel

  
    import pytz
    from datetime import datetime

    @app.template_filter('hora_br')
    def hora_br(dt):
        if not dt:
            return "-"
        
        tz = pytz.timezone("America/Sao_Paulo")

        # 🔥 garante que o datetime é UTC
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)

        return dt.astimezone(tz).strftime("%d/%m/%Y %H:%M")

    if config_override:
        app.config.update(config_override)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    _configurar_login()

    if not app.config.get("TESTING"):
        iniciar_firebase()
    _registrar_rotas_internas(app)
    _registrar_blueprints(app)
    init_financeiro_dash(app)

    if not app.config.get("TESTING"):
        _iniciar_scheduler(app)

    return app



app = create_app()


if __name__ == "__main__":
    app.run(debug=True)

