"""Rota que registra o aceite ou o ajuste da nota."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import obter_sessao
from app.models import Correcao
from app.revisao.servico import RevisaoInvalida, registrar_revisao

router = APIRouter(tags=["revisao"])


def _numero(texto: str | None) -> float | None:
    if texto is None or not str(texto).strip():
        return None
    try:
        return float(str(texto).strip().replace(",", "."))
    except ValueError:
        return None


@router.post("/correcoes/{correcao_id}/revisao")
async def revisar(request: Request, correcao_id: int, sessao: Session = Depends(obter_sessao)):
    correcao = sessao.get(Correcao, correcao_id)
    if correcao is None or correcao.submissao_id is None:
        raise HTTPException(status_code=404, detail="Correção não encontrada")
    destino = f"/respostas/{correcao.submissao_id}"

    formulario = await request.form()
    acao = formulario.get("acao")
    if acao == "aceitar":
        digitada = _numero(formulario.get("nota_final"))
        if digitada is not None and abs(digitada - correcao.nota_sugerida) > 1e-9:
            return _voltar_com_erro(
                destino, correcao_id,
                "Você digitou outra nota e clicou em aceitar a sugerida. Use \"Registrar outra nota\" "
                "para gravar a nota digitada, ou apague o campo para aceitar a sugestão.",
            )
        nota_final = correcao.nota_sugerida
    elif acao == "ajustar":
        nota_final = _numero(formulario.get("nota_final"))
        if nota_final is None:
            return _voltar_com_erro(destino, correcao_id, "Informe a nota final, por exemplo 7,5.")
    else:
        raise HTTPException(status_code=400, detail="Ação deve ser 'aceitar' ou 'ajustar'.")

    try:
        registrar_revisao(sessao, correcao, nota_final, formulario.get("comentario"),
                          usuario_id=request.state.usuario.id)
    except RevisaoInvalida as erro:
        return _voltar_com_erro(destino, correcao_id, str(erro))
    return RedirectResponse(f"{destino}#correcao-{correcao_id}", status_code=303)


def _voltar_com_erro(destino: str, correcao_id: int, mensagem: str) -> RedirectResponse:
    return RedirectResponse(
        f"{destino}?erro_revisao={correcao_id}&mensagem={quote(mensagem)}#correcao-{correcao_id}",
        status_code=303,
    )
