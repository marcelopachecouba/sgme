import os
from flask import Flask, jsonify, request, send_from_directory
from flask_login import LoginManager, login_required, current_user
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler

from models import db, Ministro

from services.firebase_service import iniciar_firebase
from services.lembrete_missa_service import enviar_lembretes_missa

from routes.auth_routes import auth_bp
from routes.dashboard_routes import dashboard_bp
from routes.ministros_routes import ministros_bp
from routes.missas_routes import missas_bp
from routes.escala_routes import escala_bp
from routes.estatisticas_routes import estatisticas_bp
from routes.publico_routes import publico_bp
from routes.admin_routes import admin_bp
from routes.avisos_routes import avisos_bp
from routes.indisponibilidade_routes import indisp_bp
from routes.casais_routes import casais_bp
from routes.presencas_routes import presencas_bp
from routes.busca_routes import busca_bp
from routes.superadmin_routes import superadmin_bp
from routes.minhas_escalas_routes import minhas_escalas_bp

from mural.mural_routes import mural_bp


# =============================
# APP
# =============================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    os.urandom(24)
)

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError("DATABASE_URL não configurada")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# =============================
# DATABASE
# =============================

db.init_app(app)

migrate = Migrate(app, db)


# =============================
# LOGIN
# =============================

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id):

    return db.session.get(Ministro, int(user_id))


# =============================
# FIREBASE
# =============================

iniciar_firebase()


# =============================
# ROTAS INTERNAS
# =============================

@app.route("/health")
def health():
    return "ok"


@app.route("/firebase-messaging-sw.js")
def firebase_sw():
    return send_from_directory(
        "static",
        "firebase-messaging-sw.js"
    )

@app.context_processor
def variaveis_globais():
    return dict(proxima=None)

@app.route("/salvar-token", methods=["POST"])
@login_required
def salvar_token():

    data = request.get_json(silent=True) or {}

    token = data.get("token")

    if token:

        current_user.firebase_token = token

        db.session.commit()

    return jsonify({"status": "ok"})


# =============================
# SCHEDULER
# =============================

scheduler = BackgroundScheduler()


def iniciar_scheduler():

    scheduler.add_job(
        enviar_lembretes_missa,
        trigger="interval",
        minutes=10,
        args=[app],
        max_instances=1,
        replace_existing=True
    )

    scheduler.start()


# iniciar scheduler apenas local
if os.getenv("FLASK_ENV") == "development":
    iniciar_scheduler()


# =============================
# BLUEPRINTS
# =============================

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
app.register_blueprint(busca_bp)
app.register_blueprint(superadmin_bp)
app.register_blueprint(minhas_escalas_bp)


# =============================
# RUN LOCAL
# =============================

if __name__ == "__main__":
    app.run(debug=True)