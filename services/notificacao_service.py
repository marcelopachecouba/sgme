from services.firebase_service import enviar_push
from services.whatsapp_service import gerar_link_whatsapp


def notificar_escala_criada(ministro, missa):

    if ministro.firebase_token:
        enviar_push(
            ministro.firebase_token,
            "Nova Escala",
            f"Você foi escalado para {missa.data.strftime('%d/%m')} às {missa.horario}"
        )

    # gera link whatsapp
    link = gerar_link_whatsapp(ministro, missa)

    return link


def notificar_escala_removida(ministro, missa):

    data = missa.data.strftime("%d/%m/%Y")

    titulo = "Escala Alterada"

    mensagem = (
        f"Você foi removido da escala.\n"
        f"Data: {data}\n"
        f"Horário: {missa.horario}\n"
        f"Comunidade: {missa.comunidade}"
    )

    if ministro.firebase_token:
        enviar_push(ministro.firebase_token, titulo, mensagem)

    link = gerar_link_whatsapp(ministro, missa)

    print("WhatsApp remoção:", link)

def notificar_confirmacao(admin, ministro, missa):

    if not admin.firebase_token:
        return

    data = missa.data.strftime("%d/%m/%Y")

    titulo = "Presença Confirmada"

    mensagem = (
        f"{ministro.nome} confirmou presença.\n"
        f"Data: {data}\n"
        f"Horário: {missa.horario}"
    )

    enviar_push(admin.firebase_token, titulo, mensagem)