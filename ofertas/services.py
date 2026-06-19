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

    # Hora atual correta no Brasil
    agora = (
        datetime.now(timezone.utc)
        .astimezone(TZ_BR)
    )

    # Consulta sempre as últimas 6 horas
    inicio_dt = (
        agora - timedelta(hours=6)
    )

    inicio_api = inicio_dt.strftime(
        "%Y-%m-%dT%H:%M:%S-03:00"
    )

    fim_api = agora.strftime(
        "%Y-%m-%dT%H:%M:%S-03:00"
    )

    print("===================================")
    print("IMPORTAÇÃO AUTOMÁTICA PIX")
    print("INÍCIO:", inicio_api)
    print("FIM   :", fim_api)
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
