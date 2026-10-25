"""Configuração dos modelos HTML e filtros usados neles."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

from app.config import FUSO, RAIZ, config

templates = Jinja2Templates(directory=RAIZ / "app" / "templates")
_FUSO = ZoneInfo(FUSO)


def numero_br(valor: float | int | None) -> str:
    """Número sem zeros sobrando e com vírgula decimal: 6.5 vira 6,5 e 10.0 vira 10."""
    if valor is None:
        return ""
    return f"{valor:g}".replace(".", ",")


def _local(data: datetime) -> datetime:
    """O SQLite devolve as datas sem fuso; elas foram gravadas em UTC."""
    if data.tzinfo is None:
        data = data.replace(tzinfo=timezone.utc)
    return data.astimezone(_FUSO)


def data_local(data: datetime | None, formato: str = "%d/%m/%Y às %H:%M") -> str:
    return _local(data).strftime(formato) if data else ""


def quando(data: datetime | None, agora: datetime | None = None) -> str:
    """Tempo relativo em português: "agora há pouco", "há 20 minutos", "ontem"."""
    if data is None:
        return ""
    local, agora = _local(data), _local(agora or datetime.now(timezone.utc))
    segundos = (agora - local).total_seconds()
    if segundos < 60:
        return "agora há pouco"
    if segundos < 3600:
        minutos = int(segundos // 60)
        return f"há {minutos} minuto{'s' if minutos > 1 else ''}"
    dias = (agora.date() - local.date()).days
    if dias == 0:
        horas = int(segundos // 3600)
        return f"há {horas} hora{'s' if horas > 1 else ''}"
    if dias == 1:
        return "ontem"
    if dias < 7:
        return f"há {dias} dias"
    return local.strftime("em %d/%m/%Y")


def saudacao(agora: datetime | None = None) -> str:
    hora = _local(agora or datetime.now(timezone.utc)).hour
    if 5 <= hora < 12:
        return "Bom dia"
    if 12 <= hora < 18:
        return "Boa tarde"
    return "Boa noite"


templates.env.filters["num"] = numero_br
templates.env.filters["data_local"] = data_local
templates.env.filters["quando"] = quando
templates.env.globals["saudacao"] = saudacao
templates.env.globals["nome_sistema"] = config.nome_sistema
templates.env.globals["modelo"] = config.modelo
