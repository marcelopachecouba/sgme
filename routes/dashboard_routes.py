from datetime import date, timedelta

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from services.dashboard_service import construir_dashboard


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def home():
    hoje = date.today()
    dados = construir_dashboard(
        id_paroquia=current_user.id_paroquia,
        inicio=hoje,
        fim=hoje + timedelta(days=7),
    )
    return render_template("dashboard.html", **dados)
