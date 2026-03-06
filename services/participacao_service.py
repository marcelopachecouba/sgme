from sqlalchemy import and_, case, func

from models import Escala, Ministro, db


def obter_estatisticas_participacao(id_paroquia):
    query = db.session.query(
        Ministro.id.label("ministro_id"),
        Ministro.nome.label("nome"),
        func.count(Escala.id).label("total_escalas"),
        func.coalesce(
            func.sum(case((Escala.confirmado.is_(True), 1), else_=0)),
            0
        ).label("confirmadas"),
        func.coalesce(
            func.sum(case((Escala.confirmado.is_(False), 1), else_=0)),
            0
        ).label("pendentes"),
    ).outerjoin(
        Escala,
        and_(
            Escala.id_ministro == Ministro.id,
            Escala.id_paroquia == id_paroquia,
        )
    ).filter(
        Ministro.id_paroquia == id_paroquia
    ).group_by(
        Ministro.id,
        Ministro.nome
    ).order_by(
        func.count(Escala.id).desc(),
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
