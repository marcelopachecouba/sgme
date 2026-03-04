from app import app
from models import db, ministro, Paroquia

with app.app_context():

    # Verifica se já existe paróquia
    paroquia = Paroquia.query.first()

    if not paroquia:
        paroquia = Paroquia(nome="Paróquia Matriz")
        db.session.add(paroquia)
        db.session.commit()
        print("Paróquia criada!")

    # Verifica se usuário já existe
    user_existente = Usuario.query.filter_by(
        email="marcelosouzapacheco@gmail.com"
    ).first()

    if not user_existente:
        user = Usuario(
            nome="Marcelo",
            email="marcelosouzapacheco@gmail.com",
            tipo="admin",
            id_paroquia=paroquia.id
        )
        user.set_senha("123456")
        db.session.add(user)
        db.session.commit()
        print("Usuário admin criado com sucesso!")
    else:
        print("Usuário já existe!")