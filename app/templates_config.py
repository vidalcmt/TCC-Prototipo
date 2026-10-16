from fastapi.templating import Jinja2Templates

from app.config import RAIZ

templates = Jinja2Templates(directory=RAIZ / "app" / "templates")
