from flask import Flask
from config import Config
from models import db, Ministro
from flask_login import LoginManager
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler

from services.firebase_service import iniciar_firebase
from services.lembrete_service import enviar_lembretes
import os

app = Flask(__name__)
app.config.from_object(Config)

# Firebase
iniciar_firebase()

# Scheduler
if os.environ.get("RENDER"):
    scheduler = BackgroundScheduler()
    scheduler.add_job(enviar_lembretes, "interval", minutes=10)
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

# Registra
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(ministros_bp)
app.register_blueprint(missas_bp)
app.register_blueprint(escala_bp)
app.register_blueprint(estatisticas_bp)
app.register_blueprint(publico_bp)
app.register_blueprint(admin_bp)

if __name__ == "__main__":
    app.run(debug=True)