from flask import Blueprint, abort, redirect, request, url_for
from flask_login import current_user

from financeiro import get_financeiro_dash

financeiro_bp = Blueprint("financeiro", __name__)

_FINANCEIRO_PAGINAS = [
    "/financeiro/dashboard",
    "/financeiro/contas",
    "/financeiro/lancamentos",
    "/financeiro/duplicatas",
    "/financeiro/importacao",
    "/financeiro/conciliacao",
    "/financeiro/padroes",
]


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


def _render_dash_index():
    dash_app = get_financeiro_dash()
    if dash_app is None:
        return redirect("/financeiro/dashboard")
    return dash_app.index()


for rota in _FINANCEIRO_PAGINAS:
    endpoint = "pagina_" + rota.rsplit("/", 1)[-1]
    financeiro_bp.add_url_rule(rota, endpoint, _render_dash_index)
