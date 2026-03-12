from datetime import datetime
import uuid

from flask import url_for
from sqlalchemy.exc import SQLAlchemyError

from models import (
    Escala,
    Ministro,
    PedidoSubstituicao,
    Missa,
    db,
)
from services.disponibilidade_service import esta_indisponivel
from services.firebase_service import enviar_push
from services.notificacao_service import notificar_escala_criada
from services.whatsapp_service import gerar_link_whatsapp_telefone, montar_mensagem_substituicao


def _tem_conflito(ministro_id, missa, id_paroquia, ignorar_escala_id=None):
    query = db.session.query(Escala).join(Missa).filter(
        Escala.id_ministro == ministro_id,
        Escala.id_paroquia == id_paroquia,
        Missa.data == missa.data,
    )
    if ignorar_escala_id:
        query = query.filter(Escala.id != ignorar_escala_id)
    return query.first() is not None
def _elegiveis_para_substituicao(escala):

    missa = escala.missa

    ministros = Ministro.query.filter_by(
        id_paroquia=escala.id_paroquia,
        comunidade=missa.comunidade,   # 🔥 FILTRO NOVO
        pode_logar=True
    ).all()

    elegiveis = []

    for ministro in ministros:

        # não pode ser o mesmo ministro
        if ministro.id == escala.id_ministro:
            continue

        # conflito de escala no mesmo dia
        if _tem_conflito(
            ministro_id=ministro.id,
            missa=missa,
            id_paroquia=escala.id_paroquia,
            ignorar_escala_id=escala.id
        ):
            continue

        # indisponibilidade
        if esta_indisponivel(
            ministro.id,
            missa,
            escala.id_paroquia
        ):
            continue

        elegiveis.append(ministro)

    return elegiveis

def criar_pedido_substituicao(escala):
    pedido_aberto = PedidoSubstituicao.query.filter_by(
        id_escala=escala.id,
        id_paroquia=escala.id_paroquia,
        status="aberto",
    ).first()
    if pedido_aberto:
        return pedido_aberto, 0, []

    pedido = PedidoSubstituicao(
        token=str(uuid.uuid4()),
        id_escala=escala.id,
        id_paroquia=escala.id_paroquia,
        id_ministro_solicitante=escala.id_ministro,
        status="aberto",
    )
    db.session.add(pedido)
    db.session.commit()

    elegiveis = _elegiveis_para_substituicao(escala)
    enviados = 0
    links_whatsapp = []
    ids_whatsapp = set()
    solicitante_nome = escala.ministro.nome if escala.ministro else "Um ministro"

    for ministro in elegiveis:
        if not ministro.token_publico:
            continue
        link = url_for(
            "escala.aceitar_substituicao_publica",
            pedido_token=pedido.token,
            ministro_token_publico=ministro.token_publico,
            _external=True,
        )
        mensagem = montar_mensagem_substituicao(
            ministro,
            escala.missa,
            solicitante_nome,
            link,
        )

        if ministro.firebase_token:
            enviar_push(
                ministro.firebase_token,
                "Pedido de Substituicao",
                mensagem,
                url=link,
            )
            enviados += 1

        if ministro.telefone and ministro.id not in ids_whatsapp:
            ids_whatsapp.add(ministro.id)
            links_whatsapp.append({
                "nome": ministro.nome,
                "link": gerar_link_whatsapp_telefone(ministro.telefone, mensagem),
            })

    return pedido, enviados, links_whatsapp


def aceitar_substituicao(pedido_token, ministro_token_publico):
    pedido = PedidoSubstituicao.query.filter_by(token=pedido_token).first()
    if not pedido:
        return False, "Pedido de substituicao nao encontrado."

    if pedido.status != "aberto":
        return False, "Este pedido ja foi atendido ou encerrado."

    ministro = Ministro.query.filter_by(token_publico=ministro_token_publico).first()
    if not ministro:
        return False, "Ministro invalido para este link."

    if ministro.id_paroquia != pedido.id_paroquia:
        return False, "Paroquia invalida para este pedido."

    escala = Escala.query.filter_by(
        id=pedido.id_escala,
        id_paroquia=pedido.id_paroquia
    ).first()
    if not escala:
        pedido.status = "cancelado"
        pedido.respondido_em = datetime.utcnow()
        db.session.commit()
        return False, "Escala original nao encontrada."

    missa = escala.missa

    if ministro.id == escala.id_ministro:
        return False, "Voce ja esta nesta escala."

    if _tem_conflito(ministro.id, missa, pedido.id_paroquia, ignorar_escala_id=escala.id):
        return False, "Voce possui conflito de escala neste dia."

    if esta_indisponivel(ministro.id, missa, pedido.id_paroquia):
        return False, "Voce esta indisponivel para esta missa."

    try:
        escala.id_ministro = ministro.id
        escala.confirmado = False
        escala.presente = False
        escala.token = str(uuid.uuid4())

        pedido.id_ministro_aceite = ministro.id
        pedido.status = "aceito"
        pedido.respondido_em = datetime.utcnow()

        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return False, "Falha ao aceitar substituicao."

    escala.missa.escala_ref = escala
    notificar_escala_criada(ministro, escala.missa)
    return True, "Substituicao aceita com sucesso."

