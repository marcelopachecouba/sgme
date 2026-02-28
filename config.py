import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY","minha_cave_secreta")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL","sqlite:///sgme.db")
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args":{"sslmode":"require"}}