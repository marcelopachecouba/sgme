from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import date

db = SQLAlchemy()


class Paroquia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    
class Ministro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120))
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    data_nascimento = db.Column(db.Date)
    tempo_ministerio = db.Column(db.Integer)
    data_cadastro = db.Column(db.Date, default=date.today)
    id_paroquia = db.Column(db.Integer, db.ForeignKey('paroquia.id'))
    token_publico = db.Column(db.String(120), unique=True,default=lambda: str(uuid.uuid4()))

    def gerar_token(self):
        self.token_publico = str(uuid.uuid4())

    __table_args__ = (
        db.UniqueConstraint('nome', 'id_paroquia', name='unique_ministro_paroquia'),
    )
    
    

class Missa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    horario = db.Column(db.String(10))
    comunidade = db.Column(db.String(100))
    qtd_ministros = db.Column(db.Integer)
    id_paroquia = db.Column(db.Integer, db.ForeignKey('paroquia.id'))    

class EscalaFixa(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    semana = db.Column(db.Integer)          # 1-5 (opcional)
    dia_semana = db.Column(db.Integer)      # 0=Segunda, 6=Domingo
    horario = db.Column(db.String(10))      # opcional
    comunidade = db.Column(db.String(100))  # opcional

    id_ministro = db.Column(
    db.Integer,
    db.ForeignKey('ministro.id', ondelete="CASCADE")) 
    
    id_paroquia = db.Column(db.Integer)

    ministro = db.relationship("Ministro", passive_deletes=True)

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(20))
    id_paroquia = db.Column(db.Integer, db.ForeignKey('paroquia.id'))
    
    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def check_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)
    

class Escala(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    id_missa = db.Column(db.Integer, db.ForeignKey('missa.id'))
    id_ministro = db.Column(db.Integer, db.ForeignKey('ministro.id'))

    confirmado = db.Column(db.Boolean, default=False)
    presente = db.Column(db.Boolean, default=False)

    id_paroquia = db.Column(db.Integer, db.ForeignKey('paroquia.id'))

    missa = db.relationship("Missa")
    ministro = db.relationship("Ministro")
    token = db.Column(db.String(100), unique=True, nullable=True)

class Indisponibilidade(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    id_ministro = db.Column(db.Integer, db.ForeignKey('ministro.id'))
    data = db.Column(db.Date, nullable=False)
    horario = db.Column(db.String(10), nullable=True)

    id_paroquia = db.Column(db.Integer, db.ForeignKey('paroquia.id'))

    ministro = db.relationship("Ministro")

