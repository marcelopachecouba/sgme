from flask import Blueprint, abort, redirect, request, url_for
from flask_login import current_user

financeiro_bp = Blueprint("financeiro", __name__)


@financeiro_bp.before_app_request
def proteger_financeiro():
    if not request.path.startswith("/financeiro"):
        return None
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    if not getattr(current_user, "is_admin", lambda: False)():
        abort(403)
    return None


@financeiro_bp.route("/financeiro")
def painel():
    return redirect("/financeiro/dashboard")
