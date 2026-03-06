import uuid

from firebase_admin import storage
from werkzeug.utils import secure_filename


def upload_arquivo(file):
    nome_original = secure_filename(file.filename)
    nome = str(uuid.uuid4()) + "_" + nome_original
    bucket = storage.bucket()
    blob = bucket.blob("mural/" + nome)
    blob.upload_from_file(file)
    blob.make_public()
    return blob.public_url
