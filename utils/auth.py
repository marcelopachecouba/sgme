from functools import wraps
from flask_login import current_user
from flask import abort

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.tipo != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated_function