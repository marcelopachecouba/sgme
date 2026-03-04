import urllib.parse

def gerar_link_whatsapp(ministro, missa):

    mensagem = f"""
Olá {ministro.nome},

Você foi escalado para servir na Eucaristia.

Data: {missa.data.strftime('%d/%m/%Y')}
Horário: {missa.horario}
Comunidade: {missa.comunidade}

Deus abençoe seu ministério.
"""

    mensagem = urllib.parse.quote(mensagem)

    telefone = ministro.telefone

    link = f"https://wa.me/55{telefone}?text={mensagem}"

    return link