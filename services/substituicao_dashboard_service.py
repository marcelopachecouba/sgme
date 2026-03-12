import uuid
from datetime import date, datetime

from flask import url_for

from models import Escala, Ministro, Missa, Substituicao, db
from services.disponibilidade_service import esta_indisponivel
from services.firebase_service import enviar_push
from services.notificacao_service import notificar_escala_criada
from services.whatsapp_service import (
    gerar_link_whatsapp_telefone,
    montar_mensagem_convite_substituicao,
    montar_mensagem_convite_troca,
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


def _buscar_escala(missa_id, ministro_id, id_paroquia):
    return Escala.query.filter_by(
        id_missa=missa_id,
        id_ministro=ministro_id,
        id_paroquia=id_paroquia,
    ).first()


def _cancelar_outras_pendencias(substituicao):
    outras_pendentes = Substituicao.query.filter(
        Substituicao.missa_id == substituicao.missa_id,
        Substituicao.ministro_original_id == substituicao.ministro_original_id,
        Substituicao.id != substituicao.id,
        Substituicao.status == "pendente",
    ).all()
    for item in outras_pendentes:
        item.status = "recusado"
        item.data_resposta = datetime.utcnow()


def _serializar_solicitacao(item):
    dados = {
        "id": item.id,
        "ministro_substituto_id": item.ministro_substituto_id,
        "nome": item.ministro_substituto.nome if item.ministro_substituto else "-",
        "status": item.status,
        "tipo": item.tipo or "substituicao",
        "data_solicitacao": item.data_solicitacao.strftime("%d/%m/%Y %H:%M"),
    }
    if item.missa_troca:
        dados["missa_troca"] = {
            "id": item.missa_troca.id,
            "data": item.missa_troca.data.strftime("%d/%m/%Y"),
            "horario": item.missa_troca.horario or "-",
            "comunidade": item.missa_troca.comunidade or "-",
        }
    return dados


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
        tipo="substituicao",
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
        "solicitacoes": [_serializar_solicitacao(item) for item in pendencias],
    }


def buscar_ministros_troca(missa, ministro_original_id):
    escala_original = _buscar_escala(missa.id, ministro_original_id, missa.id_paroquia)
    if not escala_original:
        return {
            "trocas": [],
            "solicitacoes": [],
        }

    pendencias = Substituicao.query.filter_by(
        missa_id=missa.id,
        ministro_original_id=ministro_original_id,
        status="pendente",
        tipo="troca",
    ).all()
    pendencias_por_missa = {
        (item.missa_troca_id, item.ministro_substituto_id): item
        for item in pendencias
        if item.missa_troca_id
    }

    escalas_candidatas = db.session.query(Escala).join(Missa).join(Ministro).filter(
        Escala.id_paroquia == missa.id_paroquia,
        Escala.id != escala_original.id,
        Missa.data >= date.today(),
    ).order_by(
        Missa.data.asc(),
        Missa.horario.asc(),
        Ministro.nome.asc(),
    ).all()

    trocas = []
    for escala_candidata in escalas_candidatas:
        ministro_candidato = escala_candidata.ministro
        missa_candidata = escala_candidata.missa
        if not ministro_candidato or not missa_candidata:
            continue
        if ministro_candidato.id == ministro_original_id:
            continue
        if missa_candidata.id == missa.id:
            continue
        if _tem_conflito_no_dia(ministro_original_id, missa_candidata, ignorar_escala_id=escala_original.id):
            continue
        if esta_indisponivel(ministro_original_id, missa_candidata, missa.id_paroquia):
            continue
        if _tem_conflito_no_dia(ministro_candidato.id, missa, ignorar_escala_id=escala_candidata.id):
            continue
        if esta_indisponivel(ministro_candidato.id, missa, missa.id_paroquia):
            continue

        pendencia = pendencias_por_missa.get((missa_candidata.id, ministro_candidato.id))
        trocas.append({
            "missa_id": missa_candidata.id,
            "escala_id": escala_candidata.id,
            "ministro_id": ministro_candidato.id,
            "nome": ministro_candidato.nome,
            "comunidade": ministro_candidato.comunidade or "-",
            "data": missa_candidata.data.strftime("%d/%m/%Y"),
            "horario": missa_candidata.horario or "-",
            "comunidade_missa": missa_candidata.comunidade or "-",
            "tem_push": bool(ministro_candidato.firebase_token),
            "tem_whatsapp": bool(ministro_candidato.telefone),
            "solicitacao_pendente": pendencia is not None,
            "substituicao_id": pendencia.id if pendencia else None,
        })

    return {
        "trocas": trocas,
        "solicitacoes": [_serializar_solicitacao(item) for item in pendencias],
    }


def solicitar_substituicao(missa, ministro_original, ministro_substituto):
    existente = Substituicao.query.filter_by(
        missa_id=missa.id,
        ministro_original_id=ministro_original.id,
        ministro_substituto_id=ministro_substituto.id,
        status="pendente",
        tipo="substituicao",
    ).first()
    if existente:
        return existente, None, False

    substituicao = Substituicao(
        missa_id=missa.id,
        ministro_original_id=ministro_original.id,
        ministro_substituto_id=ministro_substituto.id,
        tipo="substituicao",
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


def solicitar_troca(missa, ministro_original, missa_troca, ministro_troca):
    existente = Substituicao.query.filter_by(
        missa_id=missa.id,
        missa_troca_id=missa_troca.id,
        ministro_original_id=ministro_original.id,
        ministro_substituto_id=ministro_troca.id,
        status="pendente",
        tipo="troca",
    ).first()
    if existente:
        return existente, None, False

    substituicao = Substituicao(
        missa_id=missa.id,
        missa_troca_id=missa_troca.id,
        ministro_original_id=ministro_original.id,
        ministro_substituto_id=ministro_troca.id,
        tipo="troca",
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

    mensagem = montar_mensagem_convite_troca(
        ministro_troca,
        ministro_original,
        missa,
        missa_troca,
        confirmar_url,
        recusar_url,
    )

    if ministro_troca.firebase_token:
        enviar_push(
            ministro_troca.firebase_token,
            "Convite de Troca",
            mensagem,
            url=painel_url,
        )

    whatsapp_link = gerar_link_whatsapp_telefone(
        ministro_troca.telefone,
        mensagem,
    )

    return substituicao, whatsapp_link, True


def excluir_substituicao_pendente(substituicao):
    if substituicao.status != "pendente":
        return False, "Somente solicitacoes pendentes podem ser excluidas."

    db.session.delete(substituicao)
    db.session.commit()
    return True, "Solicitacao removida com sucesso."


def _processar_resposta_troca(substituicao, acao):
    missa_origem = Missa.query.filter_by(id=substituicao.missa_id).first()
    missa_troca = Missa.query.filter_by(id=substituicao.missa_troca_id).first()
    if not missa_origem or not missa_troca:
        return False, "Missa da troca nao encontrada."

    if acao == "recusar":
        substituicao.status = "recusado"
        substituicao.data_resposta = datetime.utcnow()
        db.session.commit()
        return True, (
            "Solicitacao de troca recusada. "
            f"Sua missa permanece em {missa_troca.data.strftime('%d/%m/%Y')} as {missa_troca.horario}."
        )

    if acao != "confirmar":
        return False, "Acao invalida."

    escala_origem = _buscar_escala(
        substituicao.missa_id,
        substituicao.ministro_original_id,
        missa_origem.id_paroquia,
    )
    escala_troca = _buscar_escala(
        substituicao.missa_troca_id,
        substituicao.ministro_substituto_id,
        missa_origem.id_paroquia,
    )
    if not escala_origem or not escala_troca:
        return False, "Uma das escalas ja foi alterada por outro ministro."

    if _tem_conflito_no_dia(
        substituicao.ministro_original_id,
        missa_troca,
        ignorar_escala_id=escala_origem.id,
    ):
        return False, "O ministro solicitante nao pode assumir sua missa atual."
    if esta_indisponivel(substituicao.ministro_original_id, missa_troca, missa_origem.id_paroquia):
        return False, "O ministro solicitante esta indisponivel para sua missa."
    if _tem_conflito_no_dia(
        substituicao.ministro_substituto_id,
        missa_origem,
        ignorar_escala_id=escala_troca.id,
    ):
        return False, "Voce ja possui outra escala no dia da missa proposta."
    if esta_indisponivel(substituicao.ministro_substituto_id, missa_origem, missa_origem.id_paroquia):
        return False, "Voce esta indisponivel para a missa proposta."

    escala_origem.id_ministro = substituicao.ministro_substituto_id
    escala_troca.id_ministro = substituicao.ministro_original_id

    for escala in (escala_origem, escala_troca):
        escala.confirmado = False
        escala.presente = False
        escala.token = str(uuid.uuid4())

    substituicao.status = "confirmado"
    substituicao.data_resposta = datetime.utcnow()
    _cancelar_outras_pendencias(substituicao)
    db.session.commit()

    escala_origem.missa.escala_ref = escala_origem
    escala_troca.missa.escala_ref = escala_troca
    if escala_origem.ministro:
        notificar_escala_criada(escala_origem.ministro, escala_origem.missa)
    if escala_troca.ministro:
        notificar_escala_criada(escala_troca.ministro, escala_troca.missa)

    return True, (
        "Troca efetuada com sucesso. "
        f"Nova missa: {missa_origem.data.strftime('%d/%m/%Y')} as {missa_origem.horario}. "
        f"Missa cedida: {missa_troca.data.strftime('%d/%m/%Y')} as {missa_troca.horario}."
    )


def processar_resposta_substituicao(substituicao, acao):
    if substituicao.status != "pendente":
        return False, "Este pedido ja foi atendido ou encerrado."

    if (substituicao.tipo or "substituicao") == "troca":
        return _processar_resposta_troca(substituicao, acao)

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

    escala = _buscar_escala(
        substituicao.missa_id,
        substituicao.ministro_original_id,
        missa.id_paroquia,
    )
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
    _cancelar_outras_pendencias(substituicao)
    db.session.commit()

    escala.missa.escala_ref = escala
    if escala.ministro:
        notificar_escala_criada(escala.ministro, escala.missa)

    return True, (
        "Substituicao efetuada com sucesso. "
        f"Data: {missa.data.strftime('%d/%m/%Y')} - Horario: {missa.horario}."
    )
