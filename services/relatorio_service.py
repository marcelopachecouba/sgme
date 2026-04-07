from datetime import datetime
from collections import defaultdict
from models import Escala
from services.observacao_lembrete_service import anexar_observacoes_ativas

def obter_saudacao():
    from datetime import datetime
    import pytz

    fuso = pytz.timezone("America/Sao_Paulo")
    hora = datetime.now(fuso).hour

    if hora < 12:
        return "Bom dia"
    elif hora < 18:
        return "Boa tarde"
    else:
        return "Boa noite"

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

def montar_mensagem_json(ministro):

    from datetime import datetime
    from collections import defaultdict

    def obter_saudacao():
        from datetime import datetime, timedelta
        hora = (datetime.utcnow() - timedelta(hours=3)).hour
        if hora < 12:
            return "Bom dia"
        elif hora < 18:
            return "Boa tarde"
        return "Boa noite"

    def semana_do_mes(dia):
        return ((dia - 1) // 7) + 1

    meses_nome = {
        1:"JANEIRO",2:"FEVEREIRO",3:"MARÇO",
        4:"ABRIL",5:"MAIO",6:"JUNHO",
        7:"JULHO",8:"AGOSTO",9:"SETEMBRO",
        10:"OUTUBRO",11:"NOVEMBRO",12:"DEZEMBRO"
    }

    dias_nome = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]

    por_mes = defaultdict(list)

    for m in ministro["missas"]:
        dia, mes, ano = map(int, m["data"].split("/"))
        por_mes[mes].append(m)

    msg = f"{obter_saudacao()} {ministro['nome']} 🙏\n\n"
    msg += "📅 *ESCALA DO PERÍODO*\n\n"

    for mes in sorted(por_mes.keys()):

        msg += "━━━━━━━━━━━━━━━\n"
        msg += f"📌 *{meses_nome[mes]}*\n"

        lista = sorted(
            por_mes[mes],
            key=lambda x: datetime.strptime(x["data"], "%d/%m/%Y")
        )

        for m in lista:

            dia = int(m["data"].split("/")[0])
            semana = semana_do_mes(dia)

            msg += (
                f"🗓 {m['data'][:2]} • "
                f"{dias_nome[m['dia_semana']]} ({semana}ª semana)\n"
                f"⏰ {m['horario']} | 📍 {m['comunidade']}\n\n"
            )

    msg += "━━━━━━━━━━━━━━━\n\n"
    msg += "🙏 Deus abençoe seu serviço!"

    return msg

def montar_mensagem_unificada(ministro, lista_escalas=None):

    from datetime import datetime, timedelta
    from collections import defaultdict

    # saudação com fuso Brasil
    hora = (datetime.utcnow() - timedelta(hours=3)).hour

    if hora < 12:
        saudacao = "Bom dia"
    elif hora < 18:
        saudacao = "Boa tarde"
    else:
        saudacao = "Boa noite"

    meses_nome = {
        1:"JANEIRO",2:"FEVEREIRO",3:"MARÇO",
        4:"ABRIL",5:"MAIO",6:"JUNHO",
        7:"JULHO",8:"AGOSTO",9:"SETEMBRO",
        10:"OUTUBRO",11:"NOVEMBRO",12:"DEZEMBRO"
    }

    dias_nome = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]

    por_mes = defaultdict(list)

    # 🔥 CASO 1 → vindo do Flask (banco)
    if lista_escalas:
        for escala in lista_escalas:
            missa = escala.missa
            por_mes[missa.data.month].append({
                "data": missa.data,
                "dia_semana": missa.data.weekday(),
                "horario": missa.horario,
                "comunidade": missa.comunidade
            })

        nome = ministro.nome

    # 🔥 CASO 2 → vindo do JSON
    else:
        for m in ministro["missas"]:
            dia, mes, ano = map(int, m["data"].split("/"))

            por_mes[mes].append({
                "data": datetime(ano, mes, dia),
                "dia_semana": m["dia_semana"],
                "horario": m["horario"],
                "comunidade": m["comunidade"]
            })

        nome = ministro["nome"]

    # montagem da mensagem
    msg = f"{saudacao} {nome} 🙏\n\n"
    msg += "📅 *ESCALA DO PERÍODO*\n\n"

    for mes in sorted(por_mes.keys()):

        msg += "━━━━━━━━━━━━━━━\n"
        msg += f"📌 *{meses_nome[mes]}*\n"

        lista = sorted(por_mes[mes], key=lambda x: x["data"])

        for m in lista:

            semana = ((m["data"].day - 1) // 7) + 1

            msg += (
                f"🗓 {m['data'].strftime('%d')} • "
                f"{dias_nome[m['dia_semana']]} ({semana}ª semana)\n"
                f"⏰ {m['horario']} | 📍 {m['comunidade']}\n\n"
            )

    msg += "━━━━━━━━━━━━━━━\n\n"
    msg += "🙏 Deus abençoe seu serviço!"

    id_paroquia = None
    if lista_escalas:
        primeira_escala = lista_escalas[0]
        id_paroquia = getattr(primeira_escala, "id_paroquia", None)
        if id_paroquia is None and getattr(primeira_escala, "missa", None):
            id_paroquia = getattr(primeira_escala.missa, "id_paroquia", None)

    return anexar_observacoes_ativas(msg, id_paroquia=id_paroquia)


def montar_mensagem_com_escala_dia(ministro, lista_escalas):
    if not lista_escalas:
        return None

    saudacao = obter_saudacao()
    meses_nome = {
        1: "JANEIRO", 2: "FEVEREIRO", 3: "MARCO",
        4: "ABRIL", 5: "MAIO", 6: "JUNHO",
        7: "JULHO", 8: "AGOSTO", 9: "SETEMBRO",
        10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO"
    }
    dias_nome = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo"]

    missa_ids = [escala.id_missa for escala in lista_escalas if escala.id_missa]
    colegas_por_missa = defaultdict(list)

    if missa_ids:
        escalas_mesma_missa = (
            Escala.query
            .join(Escala.ministro)
            .filter(Escala.id_missa.in_(missa_ids))
            .order_by(Escala.id_missa)
            .all()
        )

        for escala in escalas_mesma_missa:
            if escala.ministro:
                colegas_por_missa[escala.id_missa].append(escala.ministro.nome)

        for missa_id in colegas_por_missa:
            colegas_por_missa[missa_id] = sorted(colegas_por_missa[missa_id])

    por_mes = defaultdict(list)
    for escala in lista_escalas:
        por_mes[escala.missa.data.month].append(escala)

    msg = f"{saudacao} {ministro.nome}!\n\n"
    msg += "*RELATORIO COMPLETO DA SUA ESCALA*\n"
    msg += "Calendario do periodo com a escala completa de ministros em cada missa.\n\n"

    for mes in sorted(por_mes.keys()):
        msg += "------------------------------\n"
        msg += f"*{meses_nome[mes]}*\n\n"

        lista = sorted(por_mes[mes], key=lambda escala: (escala.missa.data, escala.missa.horario or "", escala.missa.comunidade or ""))

        for escala in lista:
            missa = escala.missa
            semana = semana_do_mes(missa.data)
            ministros_escala = colegas_por_missa.get(escala.id_missa, [])
            escala_texto = ", ".join(ministros_escala) if ministros_escala else "Nenhum ministro nesta missa"

            msg += (
                f"{missa.data.strftime('%d/%m')} - {dias_nome[missa.data.weekday()]} ({semana}a semana)\n"
                f"Horario: {missa.horario}\n"
                f"Escala: {escala_texto}\n\n"
            )

    msg += "Deus abencoe seu servico!"
    return msg
