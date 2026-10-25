from fastapi.templating import Jinja2Templates

from app.config import RAIZ

templates = Jinja2Templates(directory=RAIZ / "app" / "templates")


def numero_br(valor: float | int | None) -> str:
    """Número sem zeros sobrando e com vírgula decimal: 6.5 vira 6,5 e 10.0 vira 10."""
    if valor is None:
        return ""
    return f"{valor:g}".replace(".", ",")


templates.env.filters["num"] = numero_br
