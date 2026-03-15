from extensions import db
from datetime import datetime

from models import PushToken, Ministro,Notificacao
from services.firebase_service import enviar_push


class NotificationManager:

    """
    Gerenciador central de notificações do SGME
    """

    # --------------------------------------------------
    # NOTIFICAÇÃO INDIVIDUAL
    # --------------------------------------------------
    @staticmethod
    def enviar(usuario_id, titulo, mensagem, url="/"):

        # salva no histórico
        notificacao = Notificacao(
            usuario_id=usuario_id,
            titulo=titulo,
            mensagem=mensagem,
            criada_em=datetime.utcnow()
        )

        db.session.add(notificacao)
        db.session.commit()

        # busca tokens ativos
        tokens = PushToken.query.filter_by(
            usuario_id=usuario_id,
            ativo=True
        ).all()

        for token_obj in tokens:

            try:

                enviar_push(
                    token=token_obj.token,
                    titulo=titulo,
                    mensagem=mensagem,
                    url=url
                )

            except Exception as e:

                erro = str(e)

                # token inválido
                if "registration-token-not-registered" in erro:
                    token_obj.ativo = False

        db.session.commit()

    # --------------------------------------------------
    # ENVIAR PARA VÁRIOS USUÁRIOS
    # --------------------------------------------------
    @staticmethod
    def enviar_para_varios(usuarios, titulo, mensagem, url="/"):

        for usuario in usuarios:

            NotificationManager.enviar(
                usuario_id=usuario.id,
                titulo=titulo,
                mensagem=mensagem,
                url=url
            )

    # --------------------------------------------------
    # NOTIFICAÇÃO PARA TODOS OS MINISTROS
    # --------------------------------------------------
    @staticmethod
    def enviar_para_todos(titulo, mensagem, url="/"):

        ministros = Ministro.query.filter_by(
            notificacoes_ativas=True
        ).all()

        for ministro in ministros:

            NotificationManager.enviar(
                usuario_id=ministro.id,
                titulo=titulo,
                mensagem=mensagem,
                url=url
            )

    # --------------------------------------------------
    # CONTADOR DE NOTIFICAÇÕES
    # --------------------------------------------------
    @staticmethod
    def contar_nao_lidas(usuario_id):

        return Notificacao.query.filter_by(
            usuario_id=usuario_id,
            lida=False
        ).count()

    # --------------------------------------------------
    # MARCAR COMO LIDA
    # --------------------------------------------------
    @staticmethod
    def marcar_lida(notificacao_id):

        notificacao = Notificacao.query.get(notificacao_id)

        if notificacao:
            notificacao.lida = True
            db.session.commit()

    # --------------------------------------------------
    # MARCAR TODAS COMO LIDAS
    # --------------------------------------------------
    @staticmethod
    def marcar_todas_lidas(usuario_id):

        Notificacao.query.filter_by(
            usuario_id=usuario_id,
            lida=False
        ).update({"lida": True})

        db.session.commit()

    # --------------------------------------------------
    # LIMPAR TOKENS INVÁLIDOS
    # --------------------------------------------------
    @staticmethod
    def limpar_tokens_inativos():

        PushToken.query.filter_by(
            ativo=False
        ).delete()

        db.session.commit()
