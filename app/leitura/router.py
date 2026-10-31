"""Rotas da leitura automática das folhas digitalizadas."""

from urllib.parse import quote

import cv2
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session, sessionmaker

from app.database import obter_fabrica_sessao, obter_sessao
from app.digitalizacao.servico import IDENTIFICADA
from app.leitura import lote
from app.leitura.servico import FALHA, ler_pagina, paginas_para_ler, recorte_da_caixa
from app.models import Atividade, Folha

router = APIRouter(prefix="/atividades", tags=["leitura"])


def _atividade(sessao: Session, atividade_id: int) -> Atividade:
    atividade = sessao.get(Atividade, atividade_id)
    if atividade is None:
        raise HTTPException(status_code=404, detail="Atividade não encontrada")
    return atividade


def _folha(sessao: Session, atividade: Atividade, folha_id: int) -> Folha:
    folha = sessao.get(Folha, folha_id)
    if folha is None or folha.atividade_id != atividade.id:
        raise HTTPException(status_code=404, detail="Folha não encontrada")
    return folha


@router.post("/{atividade_id}/digitalizacoes/ler")
def ler_todas(request: Request, atividade_id: int, sessao: Session = Depends(obter_sessao),
              fabrica: sessionmaker = Depends(obter_fabrica_sessao)):
    atividade = _atividade(sessao, atividade_id)
    destino = f"/atividades/{atividade.id}/digitalizacoes"
    if not paginas_para_ler(sessao, atividade):
        return RedirectResponse(f"{destino}?aviso={quote('Não há páginas identificadas esperando leitura.')}#leitura",
                                status_code=303)
    if lote.iniciar(fabrica, atividade.id, request.state.usuario.id) is None:
        return RedirectResponse(f"{destino}?aviso={quote('Já há uma leitura em andamento.')}#leitura", status_code=303)
    return RedirectResponse(f"{destino}#leitura", status_code=303)


@router.post("/{atividade_id}/folhas/{folha_id:int}/ler")
def ler_folha(request: Request, atividade_id: int, folha_id: int, sessao: Session = Depends(obter_sessao)):
    """Lê de novo as páginas desta folha, na hora. Útil depois de ligar uma página à mão."""
    atividade = _atividade(sessao, atividade_id)
    folha = _folha(sessao, atividade, folha_id)
    paginas = [p for p in folha.digitalizacoes if p.situacao == IDENTIFICADA]
    falhas = sum(1 for p in paginas if ler_pagina(sessao, p, request.state.usuario.id).situacao == FALHA)
    if not paginas:
        mensagem = "Esta folha não tem páginas digitalizadas."
    elif falhas:
        mensagem = f"{falhas} de {len(paginas)} páginas não puderam ser lidas; veja o motivo abaixo."
    else:
        mensagem = "Leitura concluída. Confira as respostas preenchidas e salve."
    return RedirectResponse(f"/atividades/{atividade.id}/folhas/{folha.id}?aviso={quote(mensagem)}", status_code=303)


@router.get("/{atividade_id}/folhas/{folha_id:int}/recorte/{campo}")
def recorte(atividade_id: int, folha_id: int, campo: str, sessao: Session = Depends(obter_sessao)):
    atividade = _atividade(sessao, atividade_id)
    imagem = recorte_da_caixa(_folha(sessao, atividade, folha_id), campo)
    if imagem is None or imagem.size == 0:
        raise HTTPException(status_code=404, detail="Recorte não disponível")
    ok, jpeg = cv2.imencode(".jpg", imagem, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return Response(jpeg.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "private, no-cache"})
