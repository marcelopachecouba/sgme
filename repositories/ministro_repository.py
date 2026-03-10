from models import Ministro


def buscar_por_nome(nome):

    return Ministro.query.filter(
        Ministro.nome.ilike(f"%{nome}%")
    ).all()


def listar_por_paroquia(id_paroquia):

    return Ministro.query.filter_by(
        id_paroquia=id_paroquia
    ).order_by(Ministro.nome).all()


def obter_por_id(id):

    return Ministro.query.get(id)