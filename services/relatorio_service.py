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

from collections import defaultdict
from datetime import datetime


def semana_do_mes(data):
    return ((data.day - 1) // 7) + 1


def montar_mensagem_calendario(ministro, escalas):

    meses_nome = {
        1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO",
        4: "ABRIL", 5: "MAIO", 6: "JUNHO",
        7: "JULHO", 8: "AGOSTO", 9: "SETEMBRO",
        10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO"
    }

    dias_nome = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]

    # 🔹 agrupar por mês
    por_mes = defaultdict(list)

    for e in escalas:
        mes = e.missa.data.month
        por_mes[mes].append(e)

    mensagem = f"Boa tarde {ministro.nome} 🙏\n\n"
    mensagem += "📅 *Sua escala por mês:*\n\n"
    mensagem += "━━━━━━━━━━━━━━━\n"

    for mes in sorted(por_mes.keys()):

        mensagem += f"📌 *{meses_nome[mes]}*\n"

        for e in sorted(por_mes[mes], key=lambda x: x.missa.data):

            missa = e.missa
            semana = semana_do_mes(missa.data)

            mensagem += (
                f"{missa.data.strftime('%d/%m')} - "
                f"{dias_nome[missa.data.weekday()]} "
                f"({semana}ª semana) - {missa.horario}\n"
            )

        mensagem += "\n"

    # comunidade (pega da primeira)
    if escalas:
        mensagem += "━━━━━━━━━━━━━━━\n"
        mensagem += f"📍 Comunidade: {escalas[0].missa.comunidade}\n\n"

    mensagem += "Deus abençoe seu serviço 🙏"

    return mensagem