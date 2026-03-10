from models import Escala, db
import uuid


def salvar_escala(missa, ministros):

    Escala.query.filter_by(id_missa=missa.id).delete()

    for ministro in ministros:

        nova = Escala(
            id_missa=missa.id,
            id_ministro=ministro.id,
            id_paroquia=missa.id_paroquia,
            token=str(uuid.uuid4())
        )

        db.session.add(nova)

    db.session.commit()