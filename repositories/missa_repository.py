from models import Missa
from sqlalchemy import extract


def listar_mes(id_paroquia, mes, ano):

    return Missa.query.filter(
        Missa.id_paroquia == id_paroquia,
        extract("month", Missa.data) == mes,
        extract("year", Missa.data) == ano
    ).all()