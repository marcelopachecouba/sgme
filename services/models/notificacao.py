from extensions import db
from datetime import datetime

class Notificacao(db.Model):
    __tablename__ = "notificacoes"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)

    titulo = db.Column(db.String(200))
    mensagem = db.Column(db.Text)

    lida = db.Column(db.Boolean, default=False)

    criada_em = db.Column(db.DateTime, default=datetime.utcnow)