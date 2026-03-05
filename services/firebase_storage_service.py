import uuid
from firebase_admin import storage

bucket = storage.bucket()

def upload_arquivo(file):

    nome = str(uuid.uuid4()) + "_" + file.filename

    blob = bucket.blob("mural/" + nome)

    blob.upload_from_file(file)

    blob.make_public()

    return blob.public_url