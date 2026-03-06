import os

class Config:

    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "y2dnh9XfXRHDlqNz6WzRmMF1orwuX7QZQtMyaI2_ZLgjvx9CqUyXS_hDGj6EjHZj5VwN2V6eHqjGGBFSc94IjQ"
    )
    REQUIRE_SECRET_KEY = os.environ.get("REQUIRE_SECRET_KEY", "0") == "1"
    if REQUIRE_SECRET_KEY and SECRET_KEY == "y2dnh9XfXRHDlqNz6WzRmMF1orwuX7QZQtMyaI2_ZLgjvx9CqUyXS_hDGj6EjHZj5VwN2V6eHqjGGBFSc94IjQ":
        raise RuntimeError("SECRET_KEY nao configurada e REQUIRE_SECRET_KEY=1.")

    # 🔥 OBRIGA usar PostgreSQL
    DATABASE_URL = os.environ.get("DATABASE_URL")

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL não configurado. Configure para usar PostgreSQL.")

    # Corrige caso venha com postgres://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = DATABASE_URL

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FIREBASE_VAPID_KEY = os.environ.get("FIREBASE_VAPID_KEY", "")

    # Escala inteligente
    ESCALA_SCORE_DIAS_SEM_SERVIR_PESO = float(os.environ.get("ESCALA_SCORE_DIAS_SEM_SERVIR_PESO", "2.8"))
    ESCALA_SCORE_CONFIABILIDADE_PESO = float(os.environ.get("ESCALA_SCORE_CONFIABILIDADE_PESO", "10"))
    ESCALA_SCORE_ESCALAS_MES_PESO = float(os.environ.get("ESCALA_SCORE_ESCALAS_MES_PESO", "5"))
    ESCALA_SCORE_ESCALAS_7_DIAS_PESO = float(os.environ.get("ESCALA_SCORE_ESCALAS_7_DIAS_PESO", "12"))
    ESCALA_SCORE_ESCALAS_14_DIAS_PESO = float(os.environ.get("ESCALA_SCORE_ESCALAS_14_DIAS_PESO", "4"))
    ESCALA_SCORE_TOTAL_HISTORICO_PESO = float(os.environ.get("ESCALA_SCORE_TOTAL_HISTORICO_PESO", "0.15"))

    ESCALA_LIMITE_DIAS_SEM_SERVIR = int(os.environ.get("ESCALA_LIMITE_DIAS_SEM_SERVIR", "45"))
    ESCALA_RESTRICAO_DIAS_RECENTES = int(os.environ.get("ESCALA_RESTRICAO_DIAS_RECENTES", "3"))
    ESCALA_RESTRICAO_MAX_7_DIAS = int(os.environ.get("ESCALA_RESTRICAO_MAX_7_DIAS", "2"))
    ESCALA_JANELA_7_DIAS = int(os.environ.get("ESCALA_JANELA_7_DIAS", "7"))
    ESCALA_JANELA_14_DIAS = int(os.environ.get("ESCALA_JANELA_14_DIAS", "14"))

    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {
            "sslmode": "require"
        }
    }
