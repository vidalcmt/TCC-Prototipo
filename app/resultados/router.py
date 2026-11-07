"""Painel de resultados de uma atividade e registro das respostas de cada folha."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.contas.sessao import verificar_limite_diario
from app.database import obter_fabrica_sessao, obter_sessao
from app.folhas.layout import letras
from app.folhas.servico import normalizar_codigo
from app.leitura.servico import campos_com_recorte, marcar_conferidas, valores_lidos
from app.models import Atividade, Folha
from app.questoes.cliente import obter_cliente_llm
from app.resultados import lote
from app.resultados.servico import (
    A_CORRIGIR, A_REVISAR, MARCACAO_MULTIPLA, RespostasInvalidas, corrigir_discursiva, discursivas_a_corrigir, gabarito,
    liberar, recolher, registrar_respostas, resultado_da_folha,
)
from app.templates_config import templates

router = APIRouter(prefix="/atividades", tags=["resultados"])


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


def _painel(atividade: Atividade, aviso: str = "") -> RedirectResponse:
    destino = f"/atividades/{atividade.id}/resultados"
    return RedirectResponse(f"{destino}?aviso={quote(aviso)}" if aviso else destino, status_code=303)


def _pagina_da_folha(folha: Folha, aviso: str = "", ancora: str = "") -> RedirectResponse:
    destino = f"/atividades/{folha.atividade_id}/folhas/{folha.id}"
    return RedirectResponse(f"{destino}?aviso={quote(aviso)}{ancora}" if aviso else destino + ancora, status_code=303)


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------

@router.get("/{atividade_id}/resultados", response_class=HTMLResponse)
def painel(request: Request, atividade_id: int, aviso: str | None = None, codigo: str | None = None,
           sessao: Session = Depends(obter_sessao)):
    atividade = _atividade(sessao, atividade_id)
    if codigo:
        procurado = normalizar_codigo(codigo)
        folha = next((f for f in atividade.folhas if f.codigo == procurado), None)
        if folha is not None:
            return _pagina_da_folha(folha)
        aviso = f"Nenhuma folha desta atividade tem o código {procurado}."

    resultados = [resultado_da_folha(sessao, f) for f in atividade.folhas]
    respondidas = [r for r in resultados if r.respondida]
    concluidas = [r for r in resultados if r.completa]
    andamento = lote.andamento(atividade.id)
    return templates.TemplateResponse(request, "resultados.html", {
        "atividade": atividade, "resultados": resultados, "aviso": aviso,
        "respondidas": len(respondidas), "concluidas": len(concluidas),
        "a_corrigir": sum(r.contar(A_CORRIGIR) for r in resultados),
        "a_revisar": sum(r.contar(A_REVISAR) for r in resultados),
        "media": sum(r.pontos for r in concluidas) / len(concluidas) if concluidas else None,
        "maximo": resultados[0].maximo if resultados else 0,
        "andamento": andamento,
        "sem_gabarito": [n for n, item in enumerate(atividade.itens, start=1)
                         if item.questao.tipo == "objetiva" and gabarito(item.questao) is None],
    })


@router.post("/{atividade_id}/resultados/corrigir")
def corrigir_pendentes(request: Request, atividade_id: int, sessao: Session = Depends(obter_sessao),
                       fabrica: sessionmaker = Depends(obter_fabrica_sessao),
                       cliente: OpenAI | None = Depends(obter_cliente_llm)):
    atividade = _atividade(sessao, atividade_id)
    usuario = request.state.usuario
    verificar_limite_diario(sessao, usuario)
    if not discursivas_a_corrigir(sessao, atividade):
        return _painel(atividade, "Não há respostas discursivas esperando correção.")
    if lote.iniciar(fabrica, atividade.id, usuario.id, cliente) is None:
        return _painel(atividade, "Já há uma correção em andamento para esta atividade.")
    return _painel(atividade)


@router.post("/{atividade_id}/resultados/liberar")
def liberar_resultados(atividade_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _atividade(sessao, atividade_id)
    liberar(sessao, atividade)
    return _painel(atividade, "Resultados liberados. Cada aluno vê a nota quando a folha dele estiver concluída.")


@router.post("/{atividade_id}/resultados/recolher")
def recolher_resultados(atividade_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _atividade(sessao, atividade_id)
    recolher(sessao, atividade)
    return _painel(atividade, "Resultados recolhidos. Os alunos não veem mais as notas.")


@router.post("/{atividade_id}/resultados/valor")
async def valor_das_objetivas(request: Request, atividade_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _atividade(sessao, atividade_id)
    texto = str((await request.form()).get("valor_objetiva", "")).strip().replace(",", ".")
    try:
        valor = float(texto)
    except ValueError:
        valor = -1
    if not 0 < valor <= 100:
        return _painel(atividade, "O valor de cada objetiva deve ser maior que 0 e no máximo 100.")
    atividade.valor_objetiva = valor
    sessao.commit()
    return _painel(atividade, "Valor das objetivas atualizado.")


# ---------------------------------------------------------------------------
# Uma folha
# ---------------------------------------------------------------------------

@router.get("/{atividade_id}/folhas/{folha_id:int}", response_class=HTMLResponse)
def pagina_da_folha(request: Request, atividade_id: int, folha_id: int, aviso: str | None = None,
                    sessao: Session = Depends(obter_sessao)):
    atividade = _atividade(sessao, atividade_id)
    folha = _folha(sessao, atividade, folha_id)
    folhas = atividade.folhas
    posicao = folhas.index(folha)
    lidos, duvidas, avisos_leitura, leitura_pendente = valores_lidos(folha)
    return templates.TemplateResponse(request, "folha_respostas.html", {
        "lidos": lidos, "duvidas": duvidas, "avisos_leitura": avisos_leitura, "leitura_pendente": leitura_pendente,
        "recortes": campos_com_recorte(folha),
        "atividade": atividade, "folha": folha, "resultado": resultado_da_folha(sessao, folha),
        "anterior": folhas[posicao - 1] if posicao > 0 else None,
        "proxima": folhas[posicao + 1] if posicao + 1 < len(folhas) else None,
        "letras": letras, "MULTIPLA": MARCACAO_MULTIPLA, "aviso": aviso,
    })


@router.post("/{atividade_id}/folhas/{folha_id:int}/respostas")
async def salvar_respostas(request: Request, atividade_id: int, folha_id: int,
                           sessao: Session = Depends(obter_sessao)):
    atividade = _atividade(sessao, atividade_id)
    folha = _folha(sessao, atividade, folha_id)
    dados = {chave: str(valor) for chave, valor in (await request.form()).items()}
    try:
        avisos = registrar_respostas(sessao, folha, dados)
    except RespostasInvalidas as erro:
        sessao.rollback()
        return _pagina_da_folha(folha, str(erro))
    marcar_conferidas(sessao, folha)
    mensagem = " ".join(["Respostas salvas."] + avisos)
    if dados.get("depois") == "proxima":
        posicao = atividade.folhas.index(folha)
        if posicao + 1 < len(atividade.folhas):
            return _pagina_da_folha(atividade.folhas[posicao + 1], f"Folha {folha.numero}: {mensagem}")
    return _pagina_da_folha(folha, mensagem)


@router.post("/{atividade_id}/folhas/{folha_id:int}/corrigir")
def corrigir_folha(request: Request, atividade_id: int, folha_id: int, sessao: Session = Depends(obter_sessao),
                   cliente: OpenAI | None = Depends(obter_cliente_llm)):
    """Corrige na hora as discursivas desta folha: poucas chamadas, a página espera."""
    atividade = _atividade(sessao, atividade_id)
    folha = _folha(sessao, atividade, folha_id)
    usuario = request.state.usuario
    pendentes = discursivas_a_corrigir(sessao, atividade, folha)
    if not pendentes:
        return _pagina_da_folha(folha, "Não há respostas discursivas esperando correção nesta folha.")
    falhas = 0
    for submissao in pendentes:
        verificar_limite_diario(sessao, usuario)
        if not corrigir_discursiva(sessao, submissao, cliente, usuario.id).sucesso:
            falhas += 1
    if falhas:
        return _pagina_da_folha(folha, f"{falhas} de {len(pendentes)} correções falharam e foram registradas nas "
                                       "métricas. Tente de novo; as que deram certo já estão gravadas.", "#discursivas")
    return _pagina_da_folha(folha, "Correção concluída. Confira cada nota sugerida e confirme.", "#discursivas")
