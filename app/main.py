"""Aplicação web do protótipo. Rodar com: uvicorn app.main:app --reload"""

from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import RAIZ, config
from app.contas.router import administracao, protegido, publico
from app.contas.sessao import (
    LimiteDiarioAtingido, NaoAutenticado, PrecisaTrocarSenha, SemPermissao, exigir_admin, exigir_login,
)
from app.atividades.router import router as router_atividades
from app.inicio import router as router_inicio
from app.metricas.router import router as router_metricas
from app.questoes.discursivas import router as router_discursivas
from app.questoes.router import router as router_questoes
from app.revisao.router import router as router_revisao
from app.templates_config import templates

# As páginas automáticas de documentação da API (/docs) ficam desligadas: o
# sistema é usado pelas páginas HTML, e no ar elas exporiam a lista de rotas.
app = FastAPI(title="Protótipo TCC: correção com feedback elaborado",
              docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=config.secret_key,
    session_cookie="sessao",
    max_age=config.duracao_sessao_horas * 3600,
    same_site="lax",           # o cookie não acompanha formulários enviados por outros sites
    https_only=config.cookie_seguro,
)
app.mount("/static", StaticFiles(directory=RAIZ / "app" / "static"), name="static")

# Rotas públicas: entrar e sair. Todo o resto exige login.
app.include_router(publico)
app.include_router(protegido)
app.include_router(administracao)

login = [Depends(exigir_login)]
app.include_router(router_inicio, dependencies=login)
# As rotas fixas das discursivas (/questoes/nova-discursiva) precisam vir antes
# da rota /questoes/{questao_id}, senão o texto seria lido como número.
app.include_router(router_discursivas, dependencies=login)
app.include_router(router_questoes, dependencies=login)
app.include_router(router_revisao, dependencies=login)
app.include_router(router_atividades, dependencies=login)
app.include_router(router_metricas, dependencies=[Depends(exigir_admin)])


@app.get("/saude")
def saude():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# O que acontece quando o acesso é recusado
# ---------------------------------------------------------------------------

@app.exception_handler(NaoAutenticado)
def para_entrar(request: Request, _erro):
    proximo = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    destino = f"/entrar?proximo={quote(proximo)}" if request.method == "GET" and proximo != "/" else "/entrar"
    return RedirectResponse(destino, status_code=303)


@app.exception_handler(PrecisaTrocarSenha)
def para_trocar_senha(request: Request, _erro):
    return RedirectResponse("/trocar-senha", status_code=303)


@app.exception_handler(SemPermissao)
def sem_permissao(request: Request, _erro):
    return templates.TemplateResponse(request, "aviso.html", {
        "titulo": "Página restrita",
        "mensagem": "Esta página é só para administradores. Se precisar dela, fale com o administrador do sistema.",
    }, status_code=403)


@app.exception_handler(LimiteDiarioAtingido)
def limite_diario(request: Request, _erro):
    return templates.TemplateResponse(request, "aviso.html", {
        "titulo": "Limite de hoje atingido",
        "mensagem": (
            f"Você já fez {config.limite_chamadas_dia} chamadas ao modelo hoje, o limite diário por usuário. "
            "O limite existe para controlar custos e volta a zero à meia-noite. "
            "Se precisar de mais, peça ao administrador para aumentar LIMITE_CHAMADAS_DIA."
        ),
    }, status_code=429)
