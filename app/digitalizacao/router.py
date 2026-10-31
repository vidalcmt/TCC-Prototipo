"""Páginas para enviar as folhas digitalizadas e conferir a identificação."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import obter_sessao
from app.digitalizacao.servico import (
    IDENTIFICADA, OUTRA_ATIVIDADE, ROTULOS, SEM_QR, DigitalizacaoInvalida, atribuir, caminho, excluir,
    paginas_da_atividade, receber,
)
from app.folhas import layout as L
from app.models import Atividade, PaginaDigitalizada
from app.templates_config import templates

router = APIRouter(prefix="/atividades", tags=["digitalizacao"])


def _atividade(sessao: Session, atividade_id: int) -> Atividade:
    atividade = sessao.get(Atividade, atividade_id)
    if atividade is None:
        raise HTTPException(status_code=404, detail="Atividade não encontrada")
    return atividade


def _pagina(sessao: Session, atividade: Atividade, pagina_id: int) -> PaginaDigitalizada:
    pagina = sessao.get(PaginaDigitalizada, pagina_id)
    if pagina is None or pagina.atividade_id != atividade.id:
        raise HTTPException(status_code=404, detail="Página não encontrada")
    return pagina


def _voltar(atividade: Atividade, aviso: str, ancora: str = "") -> RedirectResponse:
    return RedirectResponse(f"/atividades/{atividade.id}/digitalizacoes?aviso={quote(aviso)}{ancora}", status_code=303)


@router.get("/{atividade_id}/digitalizacoes", response_class=HTMLResponse)
def pagina(request: Request, atividade_id: int, aviso: str | None = None, sessao: Session = Depends(obter_sessao)):
    atividade = _atividade(sessao, atividade_id)
    paginas = paginas_da_atividade(sessao, atividade)
    identificadas = [p for p in paginas if p.situacao == IDENTIFICADA]
    por_folha = {}
    for p in identificadas:
        por_folha.setdefault(p.folha_id, []).append(p.pagina)
    total_paginas = len(L.montar(atividade, atividade.linhas_por_resposta)) if atividade.folhas else 0
    return templates.TemplateResponse(request, "digitalizacoes.html", {
        "atividade": atividade, "aviso": aviso, "rotulos": ROTULOS,
        "pendentes": [p for p in paginas if p.situacao in (SEM_QR, OUTRA_ATIVIDADE)],
        "identificadas": len(identificadas), "por_folha": por_folha, "paginas_por_folha": total_paginas,
        "completas": sum(1 for v in por_folha.values() if len(set(v)) == total_paginas),
    })


@router.post("/{atividade_id}/digitalizacoes")
async def enviar(request: Request, atividade_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _atividade(sessao, atividade_id)
    if not atividade.folhas:
        return _voltar(atividade, "Gere as folhas de resposta antes de enviar digitalizações.")
    formulario = await request.form()
    arquivos = [(f.filename or "arquivo", await f.read()) for f in formulario.getlist("arquivos")
                if hasattr(f, "read") and f.filename]
    if not arquivos:
        return _voltar(atividade, "Escolha ao menos um arquivo.")
    try:
        resumo = receber(sessao, atividade, arquivos, request.state.usuario.id)
    except DigitalizacaoInvalida as erro:
        return _voltar(atividade, str(erro))
    return _voltar(atividade, resumo.texto())


@router.get("/{atividade_id}/digitalizacoes/{pagina_id}/imagem")
def imagem(atividade_id: int, pagina_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _atividade(sessao, atividade_id)
    arquivo = caminho(_pagina(sessao, atividade, pagina_id))
    if not arquivo.is_file():
        raise HTTPException(status_code=404, detail="Arquivo da imagem não encontrado")
    return FileResponse(arquivo, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/{atividade_id}/digitalizacoes/{pagina_id}/atribuir")
async def indicar_folha(request: Request, atividade_id: int, pagina_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _atividade(sessao, atividade_id)
    pagina_digitalizada = _pagina(sessao, atividade, pagina_id)
    dados = await request.form()
    numero = str(dados.get("pagina", "1")).strip()
    try:
        atribuir(sessao, pagina_digitalizada, atividade, str(dados.get("codigo", "")),
                 int(numero) if numero.isdigit() else 0, len(L.montar(atividade, atividade.linhas_por_resposta)))
    except DigitalizacaoInvalida as erro:
        return _voltar(atividade, str(erro), f"#pagina-{pagina_id}")
    return _voltar(atividade, "Página ligada à folha.", "#pendentes")


@router.post("/{atividade_id}/digitalizacoes/{pagina_id}/excluir")
def excluir_pagina(atividade_id: int, pagina_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _atividade(sessao, atividade_id)
    excluir(sessao, _pagina(sessao, atividade, pagina_id))
    return _voltar(atividade, "Página excluída.", "#pendentes")
