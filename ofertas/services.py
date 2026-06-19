from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from extensions import db

from models import (
    OfertaRecebida,
    Comunidade
)

from ofertas.sicredi_service import buscar_pix_sicredi

def importar_pix_automatico():

    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo

    TZ_BR = ZoneInfo("America/Sao_Paulo")

    # ===========================
    # Última contribuição gravada
    # ===========================

    ultima = (
        OfertaRecebida.query
        .order_by(
            OfertaRecebida.datahora.desc()
        )
        .first()
    )

    if ultima:

        # margem de segurança
        inicio_dt = (
            ultima.datahora -
            timedelta(seconds=10)
        )

        inicio_dt = inicio_dt.replace(
            tzinfo=TZ_BR
        )

    else:

        # primeira importação
        inicio_dt = (
            datetime.now(TZ_BR)
            - timedelta(days=30)
        )

    # horário atual oficial do Brasil
    agora = datetime.now(TZ_BR)

    # nunca consulta horário futuro
    if inicio_dt > agora:
        inicio_dt = agora - timedelta(minutes=1)

    inicio_api = inicio_dt.isoformat(
        timespec="seconds"
    )

    fim_api = agora.isoformat(
        timespec="seconds"
    )

    print("===================================")
    print("IMPORTAÇÃO AUTOMÁTICA PIX")
    print("ULTIMA OFERTA :", ultima.datahora if ultima else "Nenhuma")
    print("INICIO API    :", inicio_api)
    print("FIM API       :", fim_api)
    print("===================================")

    try:

        lista = buscar_pix_sicredi(

            inicio=inicio_api,

            fim=fim_api

        )

    except Exception as e:

        print("ERRO API PIX:", str(e))

        return str(e)

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
            pix.get("txid") or ""
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

                oferta.datahora = agora.replace(
                    tzinfo=None
                )

        else:

            oferta.datahora = agora.replace(
                tzinfo=None
            )

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
            f"IMPORTADO: {txid} - "
            f"{oferta.valor:.2f}"
        )

    db.session.commit()

    print("===================================")
    print("PIX API.....:", len(lista))
    print("IMPORTADOS..:", total)
    print("DUPLICADOS..:", duplicados)
    print("IGNORADOS...:", ignorados)
    print("===================================")

    return total 
