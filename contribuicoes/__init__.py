from flask import Blueprint

contribuicoes_bp = Blueprint(
    "contribuicoes",
    __name__,
    url_prefix="/contribuicoes"
)

from . import routes