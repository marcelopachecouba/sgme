import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_DEV_SECRET_KEY = 'dev-secret-key-change-me'


def _load_local_env():
    base_dir = Path(__file__).resolve().parent
    env_paths = [base_dir / '.env', base_dir / 'instance' / '.env']

    for env_path in env_paths:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding='utf-8').splitlines():
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_local_env()


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    if not database_url.startswith('postgresql://'):
        return database_url

    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault('sslmode', os.environ.get('DATABASE_SSLMODE', 'require'))
    database_hostaddr = os.environ.get('DATABASE_HOSTADDR', '').strip()
    if database_hostaddr:
        query['hostaddr'] = database_hostaddr
    query_string = urlencode(query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query_string, parts.fragment))


class Config:

    SECRET_KEY = os.environ.get(
        'SECRET_KEY',
        DEFAULT_DEV_SECRET_KEY
    )
    REQUIRE_SECRET_KEY = os.environ.get('REQUIRE_SECRET_KEY', '0') == '1'
    if REQUIRE_SECRET_KEY and SECRET_KEY == DEFAULT_DEV_SECRET_KEY:
        raise RuntimeError('SECRET_KEY nao configurada e REQUIRE_SECRET_KEY=1.')

    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        raise RuntimeError('DATABASE_URL nao configurado. Configure para usar PostgreSQL.')

    DATABASE_URL = _normalize_database_url(DATABASE_URL)

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FIREBASE_VAPID_KEY = os.environ.get('FIREBASE_VAPID_KEY', '')
    PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
    if not PUBLIC_BASE_URL:
        PUBLIC_BASE_URL = os.environ.get('RENDER_EXTERNAL_URL', '').strip().rstrip('/')
    if not PUBLIC_BASE_URL:
        PUBLIC_BASE_URL = 'http://localhost:5000'
    WHATSAPP_TOKEN = os.environ.get('WHATSAPP_TOKEN', '').strip()
    PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID', '').strip()
    WHATSAPP_GRAPH_VERSION = os.environ.get('WHATSAPP_GRAPH_VERSION', 'v19.0').strip()
    WHATSAPP_SEND_MODE = os.environ.get('WHATSAPP_SEND_MODE', 'template').strip().lower()
    WHATSAPP_TEMPLATE_NAME = os.environ.get('WHATSAPP_TEMPLATE_NAME', '').strip()
    WHATSAPP_TEMPLATE_LANGUAGE = os.environ.get('WHATSAPP_TEMPLATE_LANGUAGE', 'pt_BR').strip()
    WHATSAPP_TEMPLATE_BUTTON_URL = os.environ.get('WHATSAPP_TEMPLATE_BUTTON_URL', '').strip()
    SCHEDULER_TIMEZONE = os.environ.get('SCHEDULER_TIMEZONE', 'America/Sao_Paulo').strip()

    ESCALA_SCORE_DIAS_SEM_SERVIR_PESO = float(os.environ.get('ESCALA_SCORE_DIAS_SEM_SERVIR_PESO', '2.8'))
    ESCALA_SCORE_CONFIABILIDADE_PESO = float(os.environ.get('ESCALA_SCORE_CONFIABILIDADE_PESO', '10'))
    ESCALA_SCORE_ESCALAS_MES_PESO = float(os.environ.get('ESCALA_SCORE_ESCALAS_MES_PESO', '5'))
    ESCALA_SCORE_ESCALAS_7_DIAS_PESO = float(os.environ.get('ESCALA_SCORE_ESCALAS_7_DIAS_PESO', '12'))
    ESCALA_SCORE_ESCALAS_14_DIAS_PESO = float(os.environ.get('ESCALA_SCORE_ESCALAS_14_DIAS_PESO', '4'))
    ESCALA_SCORE_TOTAL_HISTORICO_PESO = float(os.environ.get('ESCALA_SCORE_TOTAL_HISTORICO_PESO', '0.15'))

    ESCALA_LIMITE_DIAS_SEM_SERVIR = int(os.environ.get('ESCALA_LIMITE_DIAS_SEM_SERVIR', '45'))
    ESCALA_RESTRICAO_DIAS_RECENTES = int(os.environ.get('ESCALA_RESTRICAO_DIAS_RECENTES', '3'))
    ESCALA_RESTRICAO_MAX_7_DIAS = int(os.environ.get('ESCALA_RESTRICAO_MAX_7_DIAS', '2'))
    ESCALA_JANELA_7_DIAS = int(os.environ.get('ESCALA_JANELA_7_DIAS', '7'))
    ESCALA_JANELA_14_DIAS = int(os.environ.get('ESCALA_JANELA_14_DIAS', '14'))
    ESCALA_CASAL_PARES = os.environ.get('ESCALA_CASAL_PARES', '')

    SQLALCHEMY_ENGINE_OPTIONS = {}
    if SQLALCHEMY_DATABASE_URI.startswith('postgresql://'):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': int(os.environ.get('DATABASE_POOL_RECYCLE', '300')),
            'connect_args': {
                'connect_timeout': int(os.environ.get('DATABASE_CONNECT_TIMEOUT', '10')),
                'keepalives': 1,
                'keepalives_idle': int(os.environ.get('DATABASE_KEEPALIVES_IDLE', '30')),
                'keepalives_interval': int(os.environ.get('DATABASE_KEEPALIVES_INTERVAL', '10')),
                'keepalives_count': int(os.environ.get('DATABASE_KEEPALIVES_COUNT', '5')),
            }
        }
