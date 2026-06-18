import requests
from flask import current_app
from rifas.sicoob_service import get_sicoob_token

#Rotina Importação Pix
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

        dados = r.json()

        todos_pix.extend(
            dados.get("pix", [])
        )

        pag = (
            dados.get("parametros", {})
                .get("paginacao", {})
        )

        print(pag)
        print(len(dados.get("pix", [])))

        if pagina >= pag.get(
            "quantidadeDePaginas",
            1
        ) - 1:

            break

        pagina += 1

    return todos_pix