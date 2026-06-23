from functools import wraps
from flask import session, redirect, url_for


def login_ofertas_required(f):

    @wraps(f)
    def decorated(*args, **kwargs):

        if not session.get(
            "ofertas_logado"
        ):

            return redirect(
                url_for(
                    "ofertas.login"
                )
            )

        return f(
            *args,
            **kwargs
        )

    return decorated

