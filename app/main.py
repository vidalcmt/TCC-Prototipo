"""Aplicação web do protótipo. Rodar com: uvicorn app.main:app --reload"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from app.config import config
from app.metricas.router import router as router_metricas
from app.templates_config import templates

app = FastAPI(title="Protótipo TCC: correção com feedback elaborado")
app.include_router(router_metricas)


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    return templates.TemplateResponse(request, "index.html", {"modelo": config.modelo})


@app.get("/saude")
def saude():
    return {"status": "ok", "modelo": config.modelo}
