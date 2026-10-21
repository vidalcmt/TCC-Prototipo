"""Aplicação web do protótipo. Rodar com: uvicorn app.main:app --reload"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from app.config import config
from app.metricas.router import router as router_metricas
from app.questoes.discursivas import router as router_discursivas
from app.questoes.router import router as router_questoes
from app.templates_config import templates

app = FastAPI(title="Protótipo TCC: correção com feedback elaborado")
app.include_router(router_metricas)
# As rotas fixas das discursivas (/questoes/nova-discursiva) precisam vir antes
# da rota /questoes/{questao_id}, senão o texto seria lido como número.
app.include_router(router_discursivas)
app.include_router(router_questoes)


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    return templates.TemplateResponse(request, "index.html", {"modelo": config.modelo})


@app.get("/saude")
def saude():
    return {"status": "ok", "modelo": config.modelo}
