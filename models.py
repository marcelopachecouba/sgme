from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

import uuid
from datetime import date
from datetime import datetime
from extensions import db


class Paroquia(db.Model):

    __tablename__ = "paroquia"

    id = db.Column(db.Integer, primary_key=True)

    nome = db.Column(db.String(150), nullable=False)

    cidade = db.Column(db.String(100))

    estado = db.Column(db.String(2))

    ativo = db.Column(db.Boolean, default=True)

    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

class Ministro(UserMixin, db.Model):

    id = db.Column(db.Integer, primary_key=True)

    nome = db.Column(db.String(120))
    nome_completo = db.Column(db.String(120))
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
    comunidade_bairro = db.Column(db.String(120))
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
        if not self.senha_hash:
            return False
        return check_password_hash(self.senha_hash, senha)

    def gerar_token(self):
        self.token_publico = str(uuid.uuid4())

    def is_admin(self):
        return self.tipo and self.tipo.lower() == "admin"

    def is_coordenador(self):
       return self.tipo and self.tipo.lower() == "coordenador"

    __table_args__ = (
        db.UniqueConstraint('nome', 'id_paroquia', name='unique_ministro_paroquia'),
    )    

class Missa(db.Model):
    
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    horario = db.Column(db.String(10))
    periodo = db.Column(db.String(20), nullable=True)
    comunidade = db.Column(db.String(100))
    qtd_ministros = db.Column(db.Integer)
    id_paroquia = db.Column(db.Integer, db.ForeignKey('paroquia.id'))  
    latitude = db.Column(db.String(50))
    longitude = db.Column(db.String(50))  

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
    token = db.Column(
        db.String(100),
        unique=True,
        nullable=False,
        default=lambda: str(uuid.uuid4())
    )

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

class IndisponibilidadeFixa(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    id_ministro = db.Column(
        db.Integer,
        db.ForeignKey("ministro.id"),
        nullable=False
    )

    id_paroquia = db.Column(
        db.Integer,
        db.ForeignKey("paroquia.id"),
        nullable=False
    )

    semana = db.Column(db.Integer)      # 1,2,3,4 ou None
    dia_semana = db.Column(db.Integer)  # 0=segunda ... 6=domingo
    horario = db.Column(db.String(10))

    ministro = db.relationship("Ministro")


class Disponibilidade(db.Model):
    __tablename__ = "disponibilidade"

    id = db.Column(db.Integer, primary_key=True)

    id_ministro = db.Column(db.Integer, db.ForeignKey("ministro.id"), nullable=False)
    data = db.Column(db.Date, nullable=False)
    horario = db.Column(db.String(10), nullable=True)

    id_paroquia = db.Column(db.Integer, db.ForeignKey("paroquia.id"), nullable=False)

    ministro = db.relationship("Ministro", lazy="joined")


class DisponibilidadeFixa(db.Model):
    __tablename__ = "disponibilidade_fixa"

    id = db.Column(db.Integer, primary_key=True)

    id_ministro = db.Column(
        db.Integer,
        db.ForeignKey("ministro.id"),
        nullable=False
    )
    id_paroquia = db.Column(
        db.Integer,
        db.ForeignKey("paroquia.id"),
        nullable=False
    )

    semana = db.Column(db.Integer)      # 1,2,3,4,5 ou None
    dia_semana = db.Column(db.Integer)  # 0=segunda ... 6=domingo
    horario = db.Column(db.String(10))

    ministro = db.relationship("Ministro")


class CasalMinisterio(db.Model):
    __tablename__ = "casal_ministerio"

    id = db.Column(db.Integer, primary_key=True)

    id_ministro_1 = db.Column(
        db.Integer,
        db.ForeignKey("ministro.id"),
        nullable=False
    )
    id_ministro_2 = db.Column(
        db.Integer,
        db.ForeignKey("ministro.id"),
        nullable=False
    )
    id_paroquia = db.Column(
        db.Integer,
        db.ForeignKey("paroquia.id"),
        nullable=False
    )
    ativo = db.Column(db.Boolean, default=True, nullable=False)

    ministro_1 = db.relationship("Ministro", foreign_keys=[id_ministro_1])
    ministro_2 = db.relationship("Ministro", foreign_keys=[id_ministro_2])


class ReuniaoFormacao(db.Model):
    __tablename__ = "reuniao_formacao"

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    assunto = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default="reuniao")  # reuniao | formacao
    observacao = db.Column(db.Text)
    foto_url = db.Column(db.String(300))
    video_url = db.Column(db.String(300))
    video_arquivo_url = db.Column(db.String(300))
    latitude = db.Column(db.String(50))
    longitude = db.Column(db.String(50))

    id_paroquia = db.Column(
        db.Integer,
        db.ForeignKey("paroquia.id"),
        nullable=False,
        index=True
    )

    presencas = db.relationship(
        "PresencaReuniao",
        backref="reuniao",
        cascade="all, delete-orphan",
        lazy="joined"
    )


class PresencaReuniao(db.Model):
    __tablename__ = "presenca_reuniao"

    id = db.Column(db.Integer, primary_key=True)

    id_reuniao = db.Column(
        db.Integer,
        db.ForeignKey("reuniao_formacao.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    id_ministro = db.Column(
        db.Integer,
        db.ForeignKey("ministro.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    id_paroquia = db.Column(
        db.Integer,
        db.ForeignKey("paroquia.id"),
        nullable=False,
        index=True
    )
    presente = db.Column(db.Boolean, nullable=False, default=True)

    ministro = db.relationship("Ministro", lazy="joined")

    __table_args__ = (
        db.UniqueConstraint(
            "id_reuniao",
            "id_ministro",
            name="uq_presenca_reuniao_ministro"
        ),
    )


class PedidoSubstituicao(db.Model):
    __tablename__ = "pedido_substituicao"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(120), unique=True, nullable=False, index=True)

    id_escala = db.Column(
        db.Integer,
        db.ForeignKey("escala.id"),
        nullable=False,
        index=True
    )
    id_paroquia = db.Column(
        db.Integer,
        db.ForeignKey("paroquia.id"),
        nullable=False,
        index=True
    )
    id_ministro_solicitante = db.Column(
        db.Integer,
        db.ForeignKey("ministro.id"),
        nullable=False,
        index=True
    )
    id_ministro_aceite = db.Column(
        db.Integer,
        db.ForeignKey("ministro.id"),
        nullable=True,
        index=True
    )

    status = db.Column(db.String(20), default="aberto", nullable=False, index=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    respondido_em = db.Column(db.DateTime, nullable=True)

    escala = db.relationship("Escala", foreign_keys=[id_escala])
    solicitante = db.relationship("Ministro", foreign_keys=[id_ministro_solicitante])
    aceite = db.relationship("Ministro", foreign_keys=[id_ministro_aceite])


class Substituicao(db.Model):
    __tablename__ = "substituicoes"

    id = db.Column(db.Integer, primary_key=True)
    missa_id = db.Column(
        db.Integer,
        db.ForeignKey("missa.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ministro_original_id = db.Column(
        db.Integer,
        db.ForeignKey("ministro.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ministro_substituto_id = db.Column(
        db.Integer,
        db.ForeignKey("ministro.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = db.Column(db.String(20), nullable=False, default="pendente", index=True)
    data_solicitacao = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    data_resposta = db.Column(db.DateTime, nullable=True)

    missa = db.relationship("Missa", lazy="joined")
    ministro_original = db.relationship("Ministro", foreign_keys=[ministro_original_id], lazy="joined")
    ministro_substituto = db.relationship("Ministro", foreign_keys=[ministro_substituto_id], lazy="joined")


class Presenca(db.Model):

    __tablename__ = "presencas"

    id = db.Column(db.Integer, primary_key=True)

    ministro_id = db.Column(
        db.Integer,
        db.ForeignKey("ministro.id"),
        nullable=False
    )

    id_missa = db.Column(
        db.Integer,
        db.ForeignKey("missa.id"),
        nullable=False
    )

    presente = db.Column(
        db.Boolean,
        default=False
    )

    data_registro = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    ministro = db.relationship(
        "Ministro",
        backref="presencas"
    )

    missa = db.relationship(
        "Missa",
        backref="presencas"
    )
