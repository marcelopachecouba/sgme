from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import date

db = SQLAlchemy()


class Paroquia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    
    ministros = db.relationship("Ministro", backref="paroquia")
    missas = db.relationship("Missa", backref="paroquia")
    

from werkzeug.security import generate_password_hash, check_password_hash

class Ministro(UserMixin, db.Model):

    id = db.Column(db.Integer, primary_key=True)

    nome = db.Column(db.String(120))
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(120), nullable=True)

    data_nascimento = db.Column(db.Date)
    tempo_ministerio = db.Column(db.Integer)
    data_cadastro = db.Column(db.Date, default=date.today)

    id_paroquia = db.Column(db.Integer, db.ForeignKey('paroquia.id'))

    token_publico = db.Column(
        db.String(120),
        unique=True,
        default=lambda: str(uuid.uuid4())
    )

    cpf = db.Column(db.String(14))
    comunidade = db.Column(db.String(30))
    firebase_token = db.Column(db.String(255))
    notificacoes_ativas = db.Column(db.Boolean, default=True)

    # 🔐 CAMPOS DE LOGIN
    senha_hash = db.Column(db.String(200), nullable=True)
    pode_logar = db.Column(db.Boolean, default=False)
    tipo = db.Column(db.String(20), default="ministro")  # admin / coordenador / ministro
    primeiro_acesso = db.Column(db.Boolean, default=True)

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def check_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    def gerar_token(self):
        self.token_publico = str(uuid.uuid4())

    __table_args__ = (
        db.UniqueConstraint('nome', 'id_paroquia', name='unique_ministro_paroquia'),
    )    

class Missa(db.Model):
    
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
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

    ministro = db.relationship("Ministro", passive_deletes=True, lazy="joined")

class Escala(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    id_missa = db.Column(db.Integer, db.ForeignKey('missa.id'), index=True)
    id_ministro = db.Column(db.Integer, db.ForeignKey('ministro.id'), index=True)

    confirmado = db.Column(db.Boolean, default=False)
    presente = db.Column(db.Boolean, default=False)

    id_paroquia = db.Column(db.Integer, db.ForeignKey('paroquia.id'))

    missa = db.relationship("Missa", lazy="joined")
    ministro = db.relationship("Ministro", lazy="joined")
    token = db.Column(db.String(100), unique=True, nullable=True)

class Indisponibilidade(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    id_ministro = db.Column(db.Integer, db.ForeignKey('ministro.id'))
    data = db.Column(db.Date, nullable=False)
    horario = db.Column(db.String(10), nullable=True)

    id_paroquia = db.Column(db.Integer, db.ForeignKey('paroquia.id'))

    ministro = db.relationship("Ministro", lazy="joined")

from datetime import datetime

class Aviso(db.Model):

    __tablename__ = "avisos"

    id = db.Column(db.Integer, primary_key=True)

    titulo = db.Column(db.String(200))
    mensagem = db.Column(db.Text)

    tipo = db.Column(db.String(50)) 
    # aviso | formacao | foto | video | pdf

    arquivo = db.Column(db.String(300))

    video_url = db.Column(db.String(300))

    fixado = db.Column(db.Boolean, default=False)

    data = db.Column(db.DateTime, default=datetime.utcnow)

class Mural(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    texto = db.Column(db.Text)

    imagem = db.Column(db.String(300))
    video = db.Column(db.String(300))

    data = db.Column(db.DateTime, default=datetime.utcnow)

    id_ministro = db.Column(db.Integer, db.ForeignKey("ministro.id"))
    id_paroquia = db.Column(db.Integer)

    ministro = db.relationship("Ministro")

from datetime import datetime

class MuralPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    texto = db.Column(db.Text)

    imagem = db.Column(db.String(300))
    video = db.Column(db.String(300))

    data = db.Column(db.DateTime, default=datetime.utcnow)

    id_ministro = db.Column(db.Integer, db.ForeignKey("ministro.id"))
    id_paroquia = db.Column(db.Integer)

    ministro = db.relationship("Ministro")


class MuralCurtida(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    id_post = db.Column(db.Integer, db.ForeignKey("mural_post.id"))
    id_ministro = db.Column(db.Integer)

    data = db.Column(db.DateTime, default=datetime.utcnow)


class MuralComentario(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    comentario = db.Column(db.Text)

    id_post = db.Column(db.Integer, db.ForeignKey("mural_post.id"))
    id_ministro = db.Column(db.Integer)

    data = db.Column(db.DateTime, default=datetime.utcnow)