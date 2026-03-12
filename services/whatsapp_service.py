import urllib.parse


def montar_mensagem_escala(ministro, missa):
    return (
        f"Ola {ministro.nome},\n\n"
        "Voce foi escalado para servir na Eucaristia.\n\n"
        f"Data: {missa.data.strftime('%d/%m/%Y')}\n"
        f"Horario: {missa.horario}\n"
        f"Comunidade: {missa.comunidade}\n\n"
        "Deus abencoe seu ministerio."
    )


def montar_mensagem_lembrete(ministro, missa):
    return (
        f"Ola {ministro.nome},\n\n"
        "Lembrete de escala no SGME.\n\n"
        f"Data: {missa.data.strftime('%d/%m/%Y')}\n"
        f"Horario: {missa.horario}\n"
        f"Comunidade: {missa.comunidade}\n\n"
        "Confirme sua participacao no aplicativo."
    )


def montar_mensagem_substituicao(destinatario, missa, solicitante_nome, link_confirmacao):
    return (
        f"Ola {destinatario.nome},\n\n"
        f"{solicitante_nome} solicitou substituicao para esta missa.\n\n"
        f"Data: {missa.data.strftime('%d/%m/%Y')}\n"
        f"Horario: {missa.horario}\n"
        f"Comunidade: {missa.comunidade}\n\n"
        f"Se puder assumir, confirme aqui:\n{link_confirmacao}"
    )


def gerar_link_whatsapp_telefone(telefone, mensagem):
    if not telefone:
        return None

    mensagem_codificada = urllib.parse.quote(mensagem)
    return f"https://wa.me/55{telefone}?text={mensagem_codificada}"


def gerar_link_whatsapp(ministro, missa):
    return gerar_link_whatsapp_telefone(
        ministro.telefone,
        montar_mensagem_escala(ministro, missa),
    )
