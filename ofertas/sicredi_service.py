import requests
import json

from flask import current_app

from rifas.sicoob_service import get_sicoob_token


def buscar_pix_sicredi(inicio, fim):

    token = get_sicoob_token()

    headers = {

        "Authorization": f"Bearer {token}"

    }

    url = current_app.config["SICREDI_API_URL"] + "/pix"

    pagina = 0

    todos_pix = []

    while True:

        params = {

            "inicio": inicio,

            "fim": fim,

            "paginaAtual": pagina,

            "itensPorPagina": 100

        }

        print("=================================")
        print("PAGINA:", pagina)
        print("PARAMS:", params)
        print("=================================")

        r = requests.get(

            url,

            headers=headers,

            params=params,

            cert=(

                current_app.config["SICREDI_CERT_PATH"],

                current_app.config["SICREDI_KEY_PATH"]

            ),

            timeout=30

        )

        print("STATUS:", r.status_code)

        print("URL:", r.url)

        print("RESPOSTA:")

        print(r.text)

        if r.status_code != 200:

            raise Exception(

                f"Erro Sicredi {r.status_code}: {r.text}"

            )

        try:

            dados = r.json()

        except Exception:

            print("JSON inválido")

            break

        pix = dados.get(

            "pix",

            []

        )

        todos_pix.extend(

            pix

        )

        pag = (

            dados.get(

                "parametros",

                {}

            ).get(

                "paginacao",

                {}

            )

        )

        print(

            "PIX:",

            len(pix)

        )

        print(

            "PAGINAÇÃO:",

            pag

        )

        if pagina >= (

            pag.get(

                "quantidadeDePaginas",

                1

            ) - 1

        ):

            break

        pagina += 1

    print("=================================")

    print(

        "TOTAL PIX:",

        len(todos_pix)

    )

    print("=================================")

    return todos_pix