from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import PushToken

push_bp = Blueprint("push", __name__)


@push_bp.route("/api/salvar-token", methods=["POST"])
@login_required
def salvar_token():

    token = request.json.get("token")
    device = request.json.get("device", "web")

    existente = PushToken.query.filter_by(
        usuario_id=current_user.id,
        token=token
    ).first()

    if not existente:

        novo = PushToken(
            usuario_id=current_user.id,
            token=token,
            device=device
        )

        db.session.add(novo)
        db.session.commit()

    return jsonify({"status": "ok"})