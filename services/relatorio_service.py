from datetime import datetime
from models import Escala

def semana_do_mes(data):
    return ((data.day - 1) // 7) + 1

def dia_semana_nome(data):
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    return dias[data.weekday()]

def gerar_relatorio_ministro(ministro, data_inicio, data_fim):

    escalas = Escala.query.join(Escala.missa).filter(
        Escala.id_ministro == ministro.id,
        Escala.confirmado == True,
        Escala.missa.has(
            data >= data_inicio,
            data <= data_fim
        )
    ).all()

    if not escalas:
        return None

    mensagem = f"Olá {ministro.nome} 🙏\n\n"
    mensagem += "Sua escala do período:\n\n"

    for e in sorted(escalas, key=lambda x: x.missa.data):

        data = e.missa.data
        semana = semana_do_mes(data)
        dia_nome = dia_semana_nome(data)

        mensagem += (
            f"{data.strftime('%d/%m')} - "
            f"{dia_nome} ({semana}ª semana) - "
            f"{e.missa.horario} - "
            f"{e.missa.comunidade}\n"
        )

    mensagem += "\nDeus abençoe seu serviço 🙏"

    return mensagem