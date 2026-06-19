from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from extensions import db

from models import (
    OfertaRecebida,
    Comunidade,
    ControleImportacaoPix
)

from ofertas.sicredi_service import buscar_pix_sicredi


def importar_pix_automatico():

    TZ_BR = ZoneInfo("America/Sao_Paulo")

    # ====================================
    # Hora atual do Brasil
    # ====================================

    agora = (
        datetime.now(timezone.utc)
        .astimezone(TZ_BR)
        .replace(tzinfo=None)
    )

    # ====================================
    # Controle da última consulta
    # ====================================

    controle = ControleImportacaoPix.query.get(1)

    if controle is None:

        controle = ControleImportacaoPix()

        controle.id = 1
        controle.ultima_consulta = agora
        controle.ultima_execucao = agora
        controle.total_importados = 0

        db.session.add(controle)
        db.session.commit()

    inicio_dt = controle.ultima_consulta

    # Segurança caso exista data futura

    if inicio_dt > agora:

        inicio_dt = agora - timedelta(minutes=1)

    # Segurança caso fique muito tempo parado

    if agora - inicio_dt > timedelta(hours=2):

        inicio_dt = agora - timedelta(hours=2)

    inicio_api = (
        inicio_dt.strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        + "-03:00"
    )

    fim_api = (
        agora.strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        + "-03:00"
    )

    print("====================================")
    print("IMPORTAÇÃO AUTOMÁTICA PIX")
    print("ULTIMA CONSULTA :", controle.ultima_consulta)
    print("INICIO API..... :", inicio_api)
    print("FIM API........ :", fim_api)
    print("====================================")

    try:

        lista = buscar_pix_sicredi(

            inicio=inicio_api,

            fim=fim_api

        )

    except Exception as e:

        print("ERRO API PIX:", str(e))

        return 0

    comunidades = {

        c.txid.strip().upper(): c

        for c in Comunidade.query.all()

        if c.txid

    }

    total = 0
    duplicados = 0
    ignorados = 0

    for pix in lista:

        txid = (

            pix.get("txid")

            or ""

        ).strip().upper()

        if not txid:

            ignorados += 1

            continue

        comunidade = comunidades.get(txid)

        if comunidade is None:

            print(
                "Comunidade não encontrada:",
                txid
            )

            ignorados += 1

            continue

        endtoendid = pix.get(
            "endToEndId",
            ""
        )

        if OfertaRecebida.query.filter_by(

            endtoendid=endtoendid

        ).first():

            duplicados += 1

            continue

        oferta = OfertaRecebida()

        oferta.txid = txid

        oferta.endtoendid = endtoendid

        oferta.codigo_autenticacao = (

            pix.get("codigoAutenticacao")

            or

            pix.get("idTransacao")

            or ""

        )

        oferta.valor = float(

            pix.get(
                "valor",
                0
            )

        )

        horario = pix.get("horario")

        if horario:

            try:

                utc = datetime.fromisoformat(

                    horario.replace(
                        "Z",
                        "+00:00"
                    )

                )

                oferta.datahora = utc.astimezone(

                    TZ_BR

                ).replace(
                    tzinfo=None
                )

            except Exception:

                oferta.datahora = agora

        else:

            oferta.datahora = agora

        oferta.chave_pix = pix.get(
            "chave",
            ""
        )

        oferta.payload = pix

        oferta.comunidade_id = comunidade.id

        oferta.tipo_id = comunidade.tipo_id

        db.session.add(oferta)

        total += 1

        print(

            f"IMPORTADO -> "

            f"{txid} | "

            f"{oferta.valor:.2f}"

        )

    # ====================================
    # Atualiza controle
    # ====================================

    controle.ultima_consulta = agora

    controle.ultima_execucao = agora

    controle.total_importados += total

    db.session.commit()

    print("====================================")
    print("PIX API..... :", len(lista))
    print("IMPORTADOS.. :", total)
    print("DUPLICADOS.. :", duplicados)
    print("IGNORADOS... :", ignorados)
    print("PRÓXIMA CONSULTA A PARTIR DE:", controle.ultima_consulta)
    print("====================================")

    return total