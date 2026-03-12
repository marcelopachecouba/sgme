import uuid
from datetime import datetime

from flask import url_for

from models import Escala, Ministro, Missa, Substituicao, db
from services.disponibilidade_service import esta_indisponivel
from services.firebase_service import enviar_push
from services.notificacao_service import notificar_escala_criada
from services.whatsapp_service import (
    gerar_link_whatsapp_telefone,
    montar_mensagem_convite_substituicao,
)


def _tem_conflito_no_dia(ministro_id, missa, ignorar_escala_id=None):
    query = db.session.query(Escala).join(Missa).filter(
        Escala.id_ministro == ministro_id,
        Escala.id_paroquia == missa.id_paroquia,
        Missa.data == missa.data,
    )
    if ignorar_escala_id:
        query = query.filter(Escala.id != ignorar_escala_id)
    return query.first() is not None


def serializar_escalados_missa(missa_id, id_paroquia):
    escalas = Escala.query.filter_by(
        id_missa=missa_id,
        id_paroquia=id_paroquia,
    ).order_by(Escala.id.asc()).all()
    return [
        {
            "escala_id": escala.id,
            "ministro_id": escala.ministro.id,
            "nome": escala.ministro.nome,
            "comunidade": escala.ministro.comunidade,
        }
        for escala in escalas
        if escala.ministro
    ]


def buscar_ministros_disponiveis(missa, ministro_original_id):
    escalados_ids = {
        row[0]
        for row in db.session.query(Escala.id_ministro).filter(
            Escala.id_missa == missa.id,
            Escala.id_paroquia == missa.id_paroquia,
        ).all()
    }

    pendencias = Substituicao.query.filter_by(
        missa_id=missa.id,
        ministro_original_id=ministro_original_id,
        status="pendente",
    ).all()
    pendencias_por_ministro = {
        item.ministro_substituto_id: item
        for item in pendencias
    }

    ministros = Ministro.query.filter_by(
        id_paroquia=missa.id_paroquia,
        pode_logar=True,
    ).order_by(Ministro.nome.asc()).all()

    disponiveis = []
    for ministro in ministros:
        if ministro.id == ministro_original_id:
            continue
        if ministro.id in escalados_ids:
            continue
        if _tem_conflito_no_dia(ministro.id, missa):
            continue
        if esta_indisponivel(ministro.id, missa, missa.id_paroquia):
            continue

        pendencia = pendencias_por_ministro.get(ministro.id)
        disponiveis.append({
            "id": ministro.id,
            "nome": ministro.nome,
            "comunidade": ministro.comunidade or "-",
            "tem_push": bool(ministro.firebase_token),
            "tem_whatsapp": bool(ministro.telefone),
            "solicitacao_pendente": pendencia is not None,
            "substituicao_id": pendencia.id if pendencia else None,
        })

    return {
        "escalados": serializar_escalados_missa(missa.id, missa.id_paroquia),
        "disponiveis": disponiveis,
        "solicitacoes": [
            {
                "id": item.id,
                "ministro_substituto_id": item.ministro_substituto_id,
                "nome": item.ministro_substituto.nome if item.ministro_substituto else "-",
                "status": item.status,
                "data_solicitacao": item.data_solicitacao.strftime("%d/%m/%Y %H:%M"),
            }
            for item in pendencias
        ],
    }


def solicitar_substituicao(missa, ministro_original, ministro_substituto):
    existente = Substituicao.query.filter_by(
        missa_id=missa.id,
        ministro_original_id=ministro_original.id,
        ministro_substituto_id=ministro_substituto.id,
        status="pendente",
    ).first()
    if existente:
        return existente, None, False

    substituicao = Substituicao(
        missa_id=missa.id,
        ministro_original_id=ministro_original.id,
        ministro_substituto_id=ministro_substituto.id,
        status="pendente",
    )
    db.session.add(substituicao)
    db.session.commit()

    confirmar_url = url_for(
        "dashboard.responder_substituicao",
        substituicao_id=substituicao.id,
        acao="confirmar",
        _external=True,
    )
    recusar_url = url_for(
        "dashboard.responder_substituicao",
        substituicao_id=substituicao.id,
        acao="recusar",
        _external=True,
    )
    painel_url = url_for(
        "dashboard.responder_substituicao",
        substituicao_id=substituicao.id,
        _external=True,
    )

    mensagem = montar_mensagem_convite_substituicao(
        ministro_substituto,
        ministro_original,
        missa,
        confirmar_url,
        recusar_url,
    )

    if ministro_substituto.firebase_token:
        enviar_push(
            ministro_substituto.firebase_token,
            "Convite de Substituicao",
            mensagem,
            url=painel_url,
        )

    whatsapp_link = gerar_link_whatsapp_telefone(
        ministro_substituto.telefone,
        mensagem,
    )

    return substituicao, whatsapp_link, True


def processar_resposta_substituicao(substituicao, acao):
    if substituicao.status != "pendente":
        return False, "Este pedido ja foi atendido ou encerrado."

    missa = Missa.query.filter_by(id=substituicao.missa_id).first()
    if not missa:
        return False, "Missa nao encontrada."

    if acao == "recusar":
        substituicao.status = "recusado"
        substituicao.data_resposta = datetime.utcnow()
        db.session.commit()
        return True, (
            "Solicitacao recusada. "
            f"Missa em {missa.data.strftime('%d/%m/%Y')} as {missa.horario}."
        )

    if acao != "confirmar":
        return False, "Acao invalida."

    escala = Escala.query.filter_by(
        id_missa=substituicao.missa_id,
        id_ministro=substituicao.ministro_original_id,
        id_paroquia=missa.id_paroquia,
    ).first()
    if not escala:
        return False, "A escala ja foi alterada por outro ministro."

    if _tem_conflito_no_dia(substituicao.ministro_substituto_id, missa, ignorar_escala_id=escala.id):
        return False, "Voce ja possui outra escala neste dia."

    if esta_indisponivel(substituicao.ministro_substituto_id, missa, missa.id_paroquia):
        return False, "Voce esta indisponivel para esta missa."

    escala.id_ministro = substituicao.ministro_substituto_id
    escala.confirmado = False
    escala.presente = False
    escala.token = str(uuid.uuid4())

    substituicao.status = "confirmado"
    substituicao.data_resposta = datetime.utcnow()

    outras_pendentes = Substituicao.query.filter(
        Substituicao.missa_id == substituicao.missa_id,
        Substituicao.ministro_original_id == substituicao.ministro_original_id,
        Substituicao.id != substituicao.id,
        Substituicao.status == "pendente",
    ).all()
    for item in outras_pendentes:
        item.status = "recusado"
        item.data_resposta = datetime.utcnow()

    db.session.commit()

    escala.missa.escala_ref = escala
    if escala.ministro:
        notificar_escala_criada(escala.ministro, escala.missa)

    return True, (
        "Troca efetuada com sucesso. "
        f"Data: {missa.data.strftime('%d/%m/%Y')} - Horario: {missa.horario}."
    )
