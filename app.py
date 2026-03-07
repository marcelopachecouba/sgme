from urllib.parse import urlparse
from flask import Flask, abort, request
from apscheduler.schedulers.background import BackgroundScheduler
from flask_login import LoginManager
from flask_migrate import Migrate
import os

from config import Config
from models import db, Ministro
from services.firebase_service import iniciar_firebase
from services.lembrete_service import enviar_lembretes
from routes.avisos_routes import avisos_bp
from routes.indisponibilidade_routes import indisp_bp
from routes.casais_routes import casais_bp
from routes.presencas_routes import presencas_bp

app = Flask(__name__)
app.config.from_object(Config)

@app.route("/health")
def health():
    return {"status": "ok"}


SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _is_same_origin(source_url: str) -> bool:
    source = urlparse(source_url)
    target = urlparse(request.host_url)
    return source.scheme == target.scheme and source.netloc == target.netloc


@app.before_request
def csrf_same_origin_protection():
    if request.method in SAFE_METHODS:
        return
    if request.endpoint == "health":
        return

    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")

    if origin:
        if not _is_same_origin(origin):
            abort(403)
        return
    if referer:
        if not _is_same_origin(referer):
            abort(403)
        return
    abort(403)

# Firebase
iniciar_firebase()

def iniciar_scheduler():
    if os.environ.get("ENABLE_SCHEDULER", "1") != "1":
        return
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        lambda: enviar_lembretes(app),
        trigger="interval",
        minutes=10
    )
    scheduler.start()

# Banco
db.init_app(app)
migrate = Migrate(app, db)

# Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"

@login_manager.user_loader
def load_user(user_id):
    return Ministro.query.get(int(user_id))

# Importa rotas
from routes.auth_routes import auth_bp
from routes.dashboard_routes import dashboard_bp
from routes.ministros_routes import ministros_bp
from routes.missas_routes import missas_bp
from routes.escala_routes import escala_bp
from routes.estatisticas_routes import estatisticas_bp
from routes.publico_routes import publico_bp
from routes.admin_routes import admin_bp
from mural.mural_routes import mural_bp

# Registra
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(ministros_bp)
app.register_blueprint(missas_bp)
app.register_blueprint(escala_bp)
app.register_blueprint(estatisticas_bp)
app.register_blueprint(publico_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(avisos_bp)
app.register_blueprint(indisp_bp)
app.register_blueprint(casais_bp)
app.register_blueprint(presencas_bp)
app.register_blueprint(mural_bp)

iniciar_scheduler()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
