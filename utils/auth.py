from functools import wraps
from flask_login import current_user
from flask import abort


def _tem_tipo(usuario, tipo):
    valor = (getattr(usuario, "tipo", "") or "").lower()
    return valor == tipo


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _tem_tipo(current_user, "admin"):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _tem_tipo(current_user, "superadmin"):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

