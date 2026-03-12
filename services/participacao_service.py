from sqlalchemy import case, func

from models import Escala, Ministro, Missa, db


def _aplicar_filtro_periodo(query, data_inicio=None, data_fim=None):
    if data_inicio:
        query = query.filter(Missa.data >= data_inicio)
    if data_fim:
        query = query.filter(Missa.data <= data_fim)
    return query


def obter_estatisticas_participacao(id_paroquia, data_inicio=None, data_fim=None):
    agregados = db.session.query(
        Escala.id_ministro.label("ministro_id"),
        func.count(Escala.id).label("total_escalas"),
        func.coalesce(
            func.sum(case((Escala.confirmado.is_(True), 1), else_=0)),
            0
        ).label("confirmadas"),
        func.coalesce(
            func.sum(case((Escala.confirmado.is_(False), 1), else_=0)),
            0
        ).label("pendentes"),
    ).join(
        Missa,
        Missa.id == Escala.id_missa
    ).filter(
        Escala.id_paroquia == id_paroquia,
        Missa.id_paroquia == id_paroquia,
    )

    agregados = _aplicar_filtro_periodo(
        agregados,
        data_inicio=data_inicio,
        data_fim=data_fim
    ).group_by(Escala.id_ministro).subquery()

    query = db.session.query(
        Ministro.id.label("ministro_id"),
        Ministro.nome.label("nome"),
        func.coalesce(agregados.c.total_escalas, 0).label("total_escalas"),
        func.coalesce(agregados.c.confirmadas, 0).label("confirmadas"),
        func.coalesce(agregados.c.pendentes, 0).label("pendentes"),
    ).outerjoin(
        agregados,
        agregados.c.ministro_id == Ministro.id
    ).filter(
        Ministro.id_paroquia == id_paroquia
    ).order_by(
        Ministro.nome.asc()
    )

    dados = []
    for row in query.all():
        total = int(row.total_escalas or 0)
        confirmadas = int(row.confirmadas or 0)
        pendentes = int(row.pendentes or 0)
        taxa_confirmacao = round((confirmadas / total) * 100, 1) if total else 0.0

        dados.append({
            "ministro_id": row.ministro_id,
            "nome": row.nome,
            "total": total,
            "confirmadas": confirmadas,
            "pendentes": pendentes,
            "taxa_confirmacao": taxa_confirmacao,
        })

    resumo = {
        "ministros": len(dados),
        "total_escalas": sum(d["total"] for d in dados),
        "confirmadas": sum(d["confirmadas"] for d in dados),
        "pendentes": sum(d["pendentes"] for d in dados),
    }

    return {"dados": dados, "resumo": resumo}


def obter_missas_ministro_periodo(ministro_id, id_paroquia, data_inicio=None, data_fim=None):
    query = db.session.query(
        Missa.data,
        Missa.horario,
        Missa.comunidade,
        Escala.confirmado,
        Escala.presente,
    ).join(
        Escala,
        Escala.id_missa == Missa.id
    ).filter(
        Escala.id_ministro == ministro_id,
        Escala.id_paroquia == id_paroquia,
        Missa.id_paroquia == id_paroquia,
    )

    query = _aplicar_filtro_periodo(
        query,
        data_inicio=data_inicio,
        data_fim=data_fim
    ).order_by(
        Missa.data.desc(),
        Missa.horario.asc()
    )

    return query.all()
