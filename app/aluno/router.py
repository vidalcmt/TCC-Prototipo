"""Página pública em que o aluno consulta o próprio resultado pelo código da folha.

Não exige login: o código, aleatório e impresso só no canhoto do aluno, é a
chave. Para dificultar tentativas de adivinhar códigos, as consultas com
código inexistente são contadas por endereço de rede e, depois de muitas,
recusadas por alguns minutos.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.aluno.servico import buscar_folha, resultado_para_o_aluno
from app.contas.sessao import ControleDeTentativas
from app.database import obter_sessao
from app.folhas.servico import normalizar_codigo
from app.templates_config import templates

router = APIRouter(tags=["aluno"])

# Uma turma inteira pode consultar da mesma rede da escola: o limite é folgado
# para erros de digitação, mas inviabiliza testar códigos em massa.
MAXIMO_ERROS_POR_REDE = 30
consultas = ControleDeTentativas(maximo=MAXIMO_ERROS_POR_REDE)

CABECALHOS = {
    "Cache-Control": "no-store",            # o resultado não fica guardado no navegador nem em proxies
    "Referrer-Policy": "no-referrer",       # o código no endereço não vaza para outros sites
    "X-Robots-Tag": "noindex, nofollow",
}


def _pagina(request: Request, nome: str, contexto: dict, status: int = 200) -> HTMLResponse:
    resposta = templates.TemplateResponse(request, nome, contexto, status_code=status)
    resposta.headers.update(CABECALHOS)
    return resposta


@router.get("/resultado", response_class=HTMLResponse)
def formulario(request: Request, codigo: str | None = None):
    if codigo:
        return RedirectResponse(f"/r/{normalizar_codigo(codigo)}", status_code=303)
    return _pagina(request, "aluno_codigo.html", {})


@router.get("/r/{codigo}", response_class=HTMLResponse)
def resultado(request: Request, codigo: str, sessao: Session = Depends(obter_sessao)):
    rede = request.client.host if request.client else "?"
    codigo = normalizar_codigo(codigo)[:20]
    if consultas.bloqueado(rede):
        return _pagina(request, "aluno_codigo.html", {
            "codigo": codigo, "erro": "Muitas tentativas com códigos inexistentes. Aguarde alguns minutos e tente de novo.",
        }, status=429)

    folha = buscar_folha(sessao, codigo)
    if folha is None:
        consultas.registrar_erro(rede)
        return _pagina(request, "aluno_codigo.html", {
            "codigo": codigo, "erro": "Código não encontrado. Confira as letras e os números no seu canhoto.",
        }, status=404)

    visivel = resultado_para_o_aluno(sessao, folha)
    if visivel is None:
        return _pagina(request, "aluno_aguarde.html", {"folha": folha, "atividade": folha.atividade})
    resultado_folha, questoes = visivel
    return _pagina(request, "aluno_resultado.html", {
        "folha": folha, "atividade": folha.atividade, "resultado": resultado_folha, "questoes": questoes,
    })
