import logging
import os
import re
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from flask import current_app, has_app_context
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import Escala, Missa
from services.public_url_service import build_public_url
from services.relatorio_service import montar_mensagem_unificada, obter_saudacao


logger = logging.getLogger(__name__)

MESES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Marco",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


def _get_config_value(chave, default=""):
    if has_app_context():
        return current_app.config.get(chave, default)
    return os.environ.get(chave, default)


def _hoje_local():
    timezone = _get_config_value("SCHEDULER_TIMEZONE", "America/Sao_Paulo")
    if not timezone:
        return date.today()
    try:
        return datetime.now(ZoneInfo(timezone)).date()
    except Exception:
        logger.warning("Timezone invalido para scheduler: %s. Usando date.today().", timezone)
        return date.today()


def _data_extenso(data):
    return f"{data.day} de {MESES_PT[data.month]} de {data.year}"


def _link_escala_publica(escala):
    if not escala or not getattr(escala, "token", None):
        return None
    return build_public_url("escala.escala_publica", token=escala.token)


def _link_calendario_publico(ministro):
    if not ministro or not getattr(ministro, "token_publico", None):
        return None
    return build_public_url("publico.calendario_publico", token=ministro.token_publico)


def montar_mensagem_lembrete(ministro, missa, escala=None):
    saudacao = obter_saudacao()
    linhas = [
        f"{saudacao} {ministro.nome.upper()},",
        "",
        "Esse e um lembrete para sua proxima escala do grupo Ministerio da Eucaristia.",
        "",
        f"Data: {_data_extenso(missa.data)}",
        f"Horario: {missa.horario}",
        f"Comunidade: {missa.comunidade}",
        "",
    ]

    link_escala = _link_escala_publica(escala)
    if link_escala:
        linhas.extend([
            "Acessar escala:",
            link_escala,
            "",
        ])

    link_calendario = _link_calendario_publico(ministro)
    if link_calendario:
        linhas.extend([
            "Ver meu calendario completo:",
            link_calendario,
        ])

    return "\n".join(linhas)


def montar_mensagem_escala(ministro, missa, escala=None):
    return montar_mensagem_lembrete(ministro, missa, escala=escala)


def montar_mensagem_substituicao(destinatario, missa, solicitante_nome, link_confirmacao):
    saudacao = obter_saudacao()
    return (
        f"{saudacao} {destinatario.nome},\n\n"
        f"{solicitante_nome} solicitou substituicao para esta missa.\n\n"
        f"Data: {missa.data.strftime('%d/%m/%Y')}\n"
        f"Horario: {missa.horario}\n"
        f"Comunidade: {missa.comunidade}\n\n"
        f"Se puder assumir, confirme aqui:\n{link_confirmacao}"
    )


def montar_mensagem_convite_substituicao(destinatario, ministro_original, missa, confirmar_url, recusar_url):
    saudacao = obter_saudacao()
    return (
        f"{saudacao} {destinatario.nome}. Voce pode substituir o ministro {ministro_original.nome} "
        f"na missa de {missa.data.strftime('%d/%m/%Y')} as {missa.horario}?\n\n"
        f"[Confirmar]\n{confirmar_url}\n\n"
        f"[Recusar]\n{recusar_url}"
    )


def montar_mensagem_convite_troca(
    destinatario,
    ministro_original,
    missa_original,
    missa_troca,
    confirmar_url,
    recusar_url,
):
    saudacao = obter_saudacao()
    return (
        f"{saudacao} {destinatario.nome}. Voce pode trocar a sua missa de "
        f"{missa_troca.data.strftime('%d/%m/%Y')} as {missa_troca.horario} "
        f"com o ministro {ministro_original.nome}, que esta na missa de "
        f"{missa_original.data.strftime('%d/%m/%Y')} as {missa_original.horario}?\n\n"
        f"[Confirmar]\n{confirmar_url}\n\n"
        f"[Recusar]\n{recusar_url}"
    )


def gerar_link_whatsapp_telefone(telefone, mensagem):
    numero = normalizar_numero_whatsapp(telefone)
    if not numero:
        return None

    mensagem_codificada = urllib.parse.quote(mensagem)
    return f"https://wa.me/{numero}?text={mensagem_codificada}"


def gerar_link_whatsapp(ministro, missa):
    return gerar_link_whatsapp_telefone(
        ministro.telefone,
        montar_mensagem_escala(ministro, missa),
    )


def normalizar_numero_whatsapp(numero, codigo_pais="55"):
    if not numero:
        return None

    apenas_digitos = re.sub(r"\D", "", str(numero))
    if not apenas_digitos:
        return None

    if apenas_digitos.startswith("00"):
        apenas_digitos = apenas_digitos[2:]

    if apenas_digitos.startswith(codigo_pais):
        return apenas_digitos

    if len(apenas_digitos) in {10, 11}:
        return f"{codigo_pais}{apenas_digitos}"

    return apenas_digitos


def enviar_whatsapp_cloud(numero, mensagem):
    token = _get_config_value("WHATSAPP_TOKEN")
    phone_number_id = _get_config_value("PHONE_NUMBER_ID")
    graph_version = _get_config_value("WHATSAPP_GRAPH_VERSION", "v19.0")

    if not token or not phone_number_id:
        raise RuntimeError("WHATSAPP_TOKEN e PHONE_NUMBER_ID precisam estar configurados.")

    numero_formatado = normalizar_numero_whatsapp(numero)
    if not numero_formatado:
        raise ValueError("Numero de telefone invalido para envio via WhatsApp.")

    url = f"https://graph.facebook.com/{graph_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": numero_formatado,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": mensagem,
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    logger.info(
        "Resposta WhatsApp Cloud API. numero=%s status=%s",
        numero_formatado,
        response.status_code,
    )

    try:
        response_body = response.json()
    except ValueError:
        response_body = {"raw": response.text}

    if not response.ok:
        logger.error(
            "Falha WhatsApp Cloud API. numero=%s status=%s resposta=%s",
            numero_formatado,
            response.status_code,
            response_body,
        )
        response.raise_for_status()

    return {
        "status_code": response.status_code,
        "body": response_body,
        "numero": numero_formatado,
    }


def buscar_escalas_para_lembrete(data_alvo, id_paroquia=None, incluir_enviadas=False):
    query = Escala.query.join(Missa).filter(Missa.data == data_alvo)

    if id_paroquia is not None:
        query = query.filter(
            Escala.id_paroquia == id_paroquia,
            Missa.id_paroquia == id_paroquia,
        )

    if not incluir_enviadas:
        query = query.filter(
            or_(
                Escala.notificacao_enviada.is_(False),
                Escala.notificacao_enviada.is_(None),
            )
        )

    return query.order_by(Escala.id_ministro.asc(), Missa.horario.asc(), Escala.id.asc()).all()


def agrupar_escalas_por_ministro(escalas):
    ministros = defaultdict(list)

    for escala in escalas:
        if not escala.ministro:
            logger.warning("Escala sem ministro associada. escala_id=%s", escala.id)
            continue
        ministros[escala.id_ministro].append(escala)

    return ministros


def enviar_lembretes_whatsapp(data_alvo=None, id_paroquia=None, forcar_envio=False):
    if data_alvo is None:
        data_alvo = _hoje_local() + timedelta(days=1)

    escalas = buscar_escalas_para_lembrete(
        data_alvo=data_alvo,
        id_paroquia=id_paroquia,
        incluir_enviadas=forcar_envio,
    )

    escalas_por_ministro = agrupar_escalas_por_ministro(escalas)
    resultado = {
        "data_alvo": data_alvo.isoformat(),
        "total_escalas": len(escalas),
        "total_ministros": len(escalas_por_ministro),
        "enviados": 0,
        "falhas": 0,
        "ministros_sem_telefone": 0,
        "detalhes": [],
    }

    for lista_escalas in escalas_por_ministro.values():
        ministro = lista_escalas[0].ministro

        if not ministro.telefone:
            logger.warning(
                "Ministro sem telefone. ministro_id=%s nome=%s",
                ministro.id,
                ministro.nome,
            )
            resultado["ministros_sem_telefone"] += 1
            resultado["detalhes"].append({
                "ministro_id": ministro.id,
                "nome": ministro.nome,
                "status": "sem_telefone",
            })
            continue

        pendentes = [
            escala for escala in lista_escalas
            if forcar_envio or not escala.notificacao_enviada
        ]
        if not pendentes:
            continue

        mensagem = montar_mensagem_unificada(ministro, pendentes)

        try:
            resposta_api = enviar_whatsapp_cloud(ministro.telefone, mensagem)
        except Exception:
            logger.exception(
                "Falha no envio do WhatsApp. ministro_id=%s nome=%s telefone=%s",
                ministro.id,
                ministro.nome,
                ministro.telefone,
            )
            resultado["falhas"] += 1
            resultado["detalhes"].append({
                "ministro_id": ministro.id,
                "nome": ministro.nome,
                "numero": ministro.telefone,
                "status": "erro_api",
            })
            continue

        try:
            for escala in pendentes:
                escala.notificacao_enviada = True
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            logger.exception(
                "WhatsApp enviado, mas nao foi possivel marcar notificacao_enviada. ministro_id=%s nome=%s",
                ministro.id,
                ministro.nome,
            )
            resultado["falhas"] += 1
            resultado["detalhes"].append({
                "ministro_id": ministro.id,
                "nome": ministro.nome,
                "numero": resposta_api["numero"],
                "status": "erro_persistencia",
            })
            continue

        logger.info(
            "WhatsApp enviado com sucesso. ministro_id=%s nome=%s numero=%s status_api=%s escalas=%s",
            ministro.id,
            ministro.nome,
            resposta_api["numero"],
            resposta_api["status_code"],
            len(pendentes),
        )
        resultado["enviados"] += 1
        resultado["detalhes"].append({
            "ministro_id": ministro.id,
            "nome": ministro.nome,
            "numero": resposta_api["numero"],
            "status": "enviado",
            "status_api": resposta_api["status_code"],
            "escalas": len(pendentes),
        })

    return resultado
