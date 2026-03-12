import urllib.parse
from flask import url_for


MESES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
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


def _data_extenso(data):
    return f"{data.day} de {MESES_PT[data.month]} de {data.year}"


def _link_escala_publica(escala):
    if not escala or not getattr(escala, "token", None):
        return None
    return url_for("escala.escala_publica", token=escala.token, _external=True)


def _link_calendario_publico(ministro):
    if not ministro or not getattr(ministro, "token_publico", None):
        return None
    return url_for("publico.calendario_publico", token=ministro.token_publico, _external=True)


def montar_mensagem_lembrete(ministro, missa, escala=None):
    linhas = [
        f"Olá {ministro.nome.upper()},",
        "",
        "Esse é um lembrete para sua próxima escala do grupo Ministério da Eucaristia.",
        "",
        f"Data: {_data_extenso(missa.data)}",
        f"Horário: {missa.horario}",
        f"Comunidade: {missa.comunidade}",
        "",
    ]

    link_escala = _link_escala_publica(escala)
    if link_escala:
        linhas.extend([
            "🔗 Acessar escala:",
            link_escala,
            "",
        ])

    link_calendario = _link_calendario_publico(ministro)
    if link_calendario:
        linhas.extend([
            "📅 Ver meu calendário completo:",
            link_calendario,
        ])

    return "\n".join(linhas)


def montar_mensagem_escala(ministro, missa, escala=None):
    return montar_mensagem_lembrete(ministro, missa, escala=escala)


def montar_mensagem_substituicao(destinatario, missa, solicitante_nome, link_confirmacao):
    return (
        f"Ola {destinatario.nome},\n\n"
        f"{solicitante_nome} solicitou substituicao para esta missa.\n\n"
        f"Data: {missa.data.strftime('%d/%m/%Y')}\n"
        f"Horario: {missa.horario}\n"
        f"Comunidade: {missa.comunidade}\n\n"
        f"Se puder assumir, confirme aqui:\n{link_confirmacao}"
    )


def montar_mensagem_convite_substituicao(destinatario, ministro_original, missa, confirmar_url, recusar_url):
    return (
        f"Ola {destinatario.nome}. Voce pode substituir o ministro {ministro_original.nome} "
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
    return (
        f"Ola {destinatario.nome}. Voce pode trocar a sua missa de "
        f"{missa_troca.data.strftime('%d/%m/%Y')} as {missa_troca.horario} "
        f"com o ministro {ministro_original.nome}, que esta na missa de "
        f"{missa_original.data.strftime('%d/%m/%Y')} as {missa_original.horario}?\n\n"
        f"[Confirmar]\n{confirmar_url}\n\n"
        f"[Recusar]\n{recusar_url}"
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
