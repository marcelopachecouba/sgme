import urllib.parse
from collections import defaultdict

from sqlalchemy.orm import joinedload

from models import Escala, Missa


def construir_dashboard(id_paroquia, inicio, fim):
    proximas_missas = Missa.query.filter(
        Missa.id_paroquia == id_paroquia,
        Missa.data >= inicio,
        Missa.data <= fim,
    ).order_by(Missa.data, Missa.horario).all()

    estrutura_missas = []
    ranking = {}

    total_escalas = Escala.query.filter_by(
        id_paroquia=id_paroquia
    ).count()
    confirmadas = Escala.query.filter_by(
        id_paroquia=id_paroquia,
        confirmado=True,
    ).count()

    missas_ids = [m.id for m in proximas_missas]
    escalas_por_missa = defaultdict(list)
    if missas_ids:
        escalas = Escala.query.options(
            joinedload(Escala.ministro)
        ).filter(
            Escala.id_paroquia == id_paroquia,
            Escala.id_missa.in_(missas_ids)
        ).all()
        for escala in escalas:
            escalas_por_missa[escala.id_missa].append(escala)

    for missa in proximas_missas:
        escalas = escalas_por_missa.get(missa.id, [])

        ministros = []
        telefones = []

        for escala in escalas:
            if not escala.ministro:
                continue
            ministros.append(escala.ministro.nome)
            ranking[escala.ministro.nome] = ranking.get(escala.ministro.nome, 0) + 1
            if escala.ministro.telefone:
                telefones.append(f"55{escala.ministro.telefone}")

        mensagem = urllib.parse.quote(
            f"Lembrete de Escala - Ministério da Eucaristia\n\n"
            f"Data: {missa.data.strftime('%d/%m/%Y')}\n"
            f"Horário: {missa.horario}\n"
            f"Comunidade: {missa.comunidade}\n\n"
            f"Deus abençoe seu ministério."
        )

        link_whatsapp = None
        if telefones:
            link_whatsapp = f"https://wa.me/{telefones[0]}?text={mensagem}"

        estrutura_missas.append({
            "missa": missa,
            "missa_id": missa.id,
            "ministros": ministros,
            "whatsapp": link_whatsapp,
        })

    mais_escalado = max(ranking, key=ranking.get) if ranking else "-"
    menos_escalado = min(ranking, key=ranking.get) if ranking else "-"

    return {
        "proximas_missas": estrutura_missas,
        "total_escalas": total_escalas,
        "confirmadas": confirmadas,
        "mais_escalado": mais_escalado,
        "menos_escalado": menos_escalado,
        "grafico_barra": None,
        "grafico_pizza": None,
    }
