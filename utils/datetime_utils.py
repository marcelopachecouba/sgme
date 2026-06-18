from datetime import datetime
from zoneinfo import ZoneInfo

TZ_BRASIL = ZoneInfo("America/Sao_Paulo")

def agora_brasil():
    return datetime.now(TZ_BRASIL)