from werkzeug.exceptions import Forbidden, NotFound

from models import Escala, EscalaFixa, Ministro, Missa


def assert_paroquia(obj, id_paroquia):
    if getattr(obj, "id_paroquia", None) != id_paroquia:
        raise Forbidden()


def get_missa_or_404(missa_id, id_paroquia):
    missa = Missa.query.get(missa_id)
    if not missa:
        raise NotFound()
    assert_paroquia(missa, id_paroquia)
    return missa


def get_ministro_or_404(ministro_id, id_paroquia):
    ministro = Ministro.query.get(ministro_id)
    if not ministro:
        raise NotFound()
    assert_paroquia(ministro, id_paroquia)
    return ministro


def get_escala_or_404(escala_id, id_paroquia):
    escala = Escala.query.get(escala_id)
    if not escala:
        raise NotFound()
    assert_paroquia(escala, id_paroquia)
    return escala


def get_escala_fixa_or_404(regra_id, id_paroquia):
    regra = EscalaFixa.query.get(regra_id)
    if not regra:
        raise NotFound()
    assert_paroquia(regra, id_paroquia)
    return regra
