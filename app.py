import os
from urllib.parse import urlparse

from flask import Flask, abort, request, jsonify, send_from_directory
from flask_login import LoginManager, login_required, current_user
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler

from models import db, Ministro
from services.firebase_service import iniciar_firebase
from services.lembrete_service import enviar_lembretes
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
from mural.mural_routes import mural_bp


# =============================
# APP
# =============================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
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
    return Ministro.query.get(int(user_id))


# =============================
# FIREBASE
# =============================

iniciar_firebase()


# =============================
# ROUTES
# =============================

@app.route("/health")
def health():
    return "ok"


@app.route('/firebase-messaging-sw.js')
def firebase_sw():
    return send_from_directory('static', 'firebase-messaging-sw.js')


@app.route("/salvar-token", methods=["POST"])
@login_required
def salvar_token():

    data = request.get_json()
    token = data.get("token")

    if token:
        current_user.firebase_token = token
        db.session.commit()

    return jsonify({"status": "ok"})


# =============================
# SCHEDULER
# =============================

def iniciar_scheduler():

    if os.environ.get("ENABLE_SCHEDULER", "1") != "1":
        return

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        enviar_lembretes_missa,
        trigger="interval",
        minutes=10,
        args=[app],
        max_instances=1
    )

    scheduler.start()


if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
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


# =============================
# RUN LOCAL
# =============================

if __name__ == "__main__":
    app.run(debug=True)