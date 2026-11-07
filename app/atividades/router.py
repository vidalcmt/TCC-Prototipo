"""Atividades: o professor junta questões já cadastradas, ordena e imprime em A4.

As atividades são uma ferramenta de uso do professor. Não entram na correção,
nas métricas nem na análise da pesquisa.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import obter_sessao
from app.folhas import layout as L
from app.folhas.servico import FolhasInvalidas, descartar_folhas, gerar_folhas, qr_svg, questoes_travadas
from app.models import Atividade, AtividadeQuestao, Questao, Usuario
from app.questoes.router import _filtrar
from app.resultados.servico import folha_tem_respostas
from app.templates_config import templates

router = APIRouter(prefix="/atividades", tags=["atividades"])

LIMITE_BUSCA = 20
LINHAS_POR_RESPOSTA = (5, 8, 12, 16)
LINHAS_PADRAO = 8


async def _formulario(request: Request) -> dict[str, str]:
    return {chave: str(valor).strip() for chave, valor in (await request.form()).items()}


def _buscar(sessao: Session, atividade_id: int) -> Atividade:
    atividade = sessao.get(Atividade, atividade_id)
    if atividade is None:
        raise HTTPException(status_code=404, detail="Atividade não encontrada")
    return atividade


AVISO_TRAVADA = ("As folhas de resposta desta atividade já foram geradas. Para mudar as questões, "
                 "descarte as folhas primeiro: as já impressas deixam de valer.")


def _voltar(atividade: Atividade, aviso: str, ancora: str = "") -> RedirectResponse:
    return RedirectResponse(f"/atividades/{atividade.id}?aviso={quote(aviso)}{ancora}", status_code=303)


def _renumerar(atividade: Atividade) -> None:
    for posicao, item in enumerate(atividade.itens, start=1):
        item.ordem = posicao


# ---------------------------------------------------------------------------
# Lista e criação
# ---------------------------------------------------------------------------

def _atividades(sessao: Session) -> list:
    """Atividades da mais recente para a mais antiga, com o número de questões e quem criou."""
    contagem = (
        select(AtividadeQuestao.atividade_id, func.count().label("n"))
        .group_by(AtividadeQuestao.atividade_id).subquery()
    )
    return sessao.execute(
        select(Atividade, func.coalesce(contagem.c.n, 0), Usuario)
        .outerjoin(contagem, contagem.c.atividade_id == Atividade.id)
        .outerjoin(Usuario, Usuario.id == Atividade.usuario_id)
        .order_by(Atividade.id.desc())
    ).all()


@router.get("", response_class=HTMLResponse)
def listar(request: Request, sessao: Session = Depends(obter_sessao)):
    return templates.TemplateResponse(request, "atividades.html",
                                      {"linhas": _atividades(sessao), "dados": {}, "erro": None})


@router.post("", response_class=HTMLResponse)
async def criar(request: Request, sessao: Session = Depends(obter_sessao)):
    dados = await _formulario(request)
    if not dados.get("titulo"):
        return templates.TemplateResponse(request, "atividades.html", {
            "linhas": _atividades(sessao), "dados": dados, "erro": "Dê um título à atividade.",
        }, status_code=400)
    atividade = Atividade(titulo=dados["titulo"], turma=dados.get("turma") or None,
                          instrucoes=dados.get("instrucoes") or None, usuario_id=request.state.usuario.id)
    sessao.add(atividade)
    sessao.commit()
    return RedirectResponse(f"/atividades/{atividade.id}", status_code=303)


# ---------------------------------------------------------------------------
# Página da atividade: questões, ordem e busca para adicionar
# ---------------------------------------------------------------------------

@router.get("/{atividade_id}", response_class=HTMLResponse)
def detalhe(request: Request, atividade_id: int, aviso: str | None = None,
            sessao: Session = Depends(obter_sessao)):
    atividade = _buscar(sessao, atividade_id)
    filtros = {nome: (request.query_params.get(nome) or "").strip()
               for nome in ("busca", "numero", "tipo", "area", "fonte", "ano", "situacao")}
    buscando = any(filtros.values())

    resultados, mais = [], False
    if buscando:
        ja_incluidas = {item.questao_id for item in atividade.itens}
        consulta = _filtrar(select(Questao), filtros).order_by(Questao.id)
        if ja_incluidas:
            consulta = consulta.where(Questao.id.not_in(ja_incluidas))
        encontradas = sessao.scalars(consulta.limit(LIMITE_BUSCA + 1)).all()
        resultados, mais = encontradas[:LIMITE_BUSCA], len(encontradas) > LIMITE_BUSCA

    return templates.TemplateResponse(request, "atividade.html", {
        "atividade": atividade, "filtros": filtros, "buscando": buscando,
        "resultados": resultados, "mais": mais, "limite": LIMITE_BUSCA,
        "autor": sessao.get(Usuario, atividade.usuario_id) if atividade.usuario_id else None,
        "aviso": aviso, "travada": questoes_travadas(atividade),
        "opcoes_linhas": LINHAS_POR_RESPOSTA, "linhas_padrao": LINHAS_PADRAO,
        "com_respostas": folha_tem_respostas(atividade),
    })


@router.post("/{atividade_id}/editar")
async def editar(request: Request, atividade_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _buscar(sessao, atividade_id)
    dados = await _formulario(request)
    if dados.get("titulo"):
        atividade.titulo = dados["titulo"]
    atividade.turma = dados.get("turma") or None
    atividade.instrucoes = dados.get("instrucoes") or None
    sessao.commit()
    return RedirectResponse(f"/atividades/{atividade.id}", status_code=303)


@router.post("/{atividade_id}/excluir")
def excluir(atividade_id: int, sessao: Session = Depends(obter_sessao)):
    """Apaga a atividade. As questões continuam cadastradas."""
    sessao.delete(_buscar(sessao, atividade_id))
    sessao.commit()
    return RedirectResponse("/atividades", status_code=303)


@router.post("/{atividade_id}/questoes")
async def adicionar(request: Request, atividade_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _buscar(sessao, atividade_id)
    if questoes_travadas(atividade):
        return _voltar(atividade, AVISO_TRAVADA, "#questoes")
    dados = await _formulario(request)
    questao_id = int(dados["questao_id"]) if dados.get("questao_id", "").isdigit() else None
    if questao_id is None or sessao.get(Questao, questao_id) is None:
        raise HTTPException(status_code=400, detail="Questão não encontrada.")
    if all(item.questao_id != questao_id for item in atividade.itens):
        atividade.itens.append(AtividadeQuestao(questao_id=questao_id, ordem=len(atividade.itens) + 1))
        sessao.commit()
    # Volta para a mesma busca, para adicionar várias questões em sequência.
    volta = dados.get("voltar", "")
    destino = volta if volta.startswith(f"/atividades/{atividade.id}") else f"/atividades/{atividade.id}"
    return RedirectResponse(destino, status_code=303)


@router.post("/{atividade_id}/questoes/{questao_id}/mover")
async def mover(request: Request, atividade_id: int, questao_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _buscar(sessao, atividade_id)
    if questoes_travadas(atividade):
        return _voltar(atividade, AVISO_TRAVADA, "#questoes")
    direcao = (await _formulario(request)).get("direcao")
    itens = list(atividade.itens)
    posicao = next((i for i, item in enumerate(itens) if item.questao_id == questao_id), None)
    if posicao is None:
        raise HTTPException(status_code=404, detail="Questão não está nesta atividade.")
    alvo = posicao - 1 if direcao == "cima" else posicao + 1
    if 0 <= alvo < len(itens):
        itens[posicao].ordem, itens[alvo].ordem = itens[alvo].ordem, itens[posicao].ordem
        sessao.commit()
    return RedirectResponse(f"/atividades/{atividade.id}#questoes", status_code=303)


@router.post("/{atividade_id}/questoes/{questao_id}/remover")
def remover(atividade_id: int, questao_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _buscar(sessao, atividade_id)
    if questoes_travadas(atividade):
        return _voltar(atividade, AVISO_TRAVADA, "#questoes")
    for item in list(atividade.itens):
        if item.questao_id == questao_id:
            atividade.itens.remove(item)
    _renumerar(atividade)
    sessao.commit()
    return RedirectResponse(f"/atividades/{atividade.id}#questoes", status_code=303)


# ---------------------------------------------------------------------------
# Impressão em A4
# ---------------------------------------------------------------------------

@router.get("/{atividade_id}/imprimir", response_class=HTMLResponse)
def imprimir(request: Request, atividade_id: int, gabarito: int = 0, linhas: int = LINHAS_PADRAO,
             sessao: Session = Depends(obter_sessao)):
    """Caderno de questões pronto para imprimir ou salvar em PDF pelo navegador.

    O caderno não identifica o aluno: é o mesmo para a turma toda. Com folhas
    de resposta geradas, as respostas vão nelas, e o caderno sai sem linhas;
    sem folhas, as discursivas trazem linhas para responder no próprio caderno.
    Com gabarito, é a versão do professor: alternativa correta marcada e, nas
    discursivas, a resposta esperada e a rubrica.
    """
    atividade = _buscar(sessao, atividade_id)
    linhas = linhas if linhas in LINHAS_POR_RESPOSTA else LINHAS_PADRAO
    # Resumo do gabarito das objetivas, pelo número da questão na folha: [(1, "B"), (3, "D")]
    resumo_objetivas = [
        (numero, a.letra)
        for numero, item in enumerate(atividade.itens, start=1) if item.questao.tipo == "objetiva"
        for a in item.questao.alternativas if a.correta
    ]
    return templates.TemplateResponse(request, "atividade_impressao.html", {
        "atividade": atividade, "gabarito": bool(gabarito), "linhas": linhas,
        "opcoes_linhas": LINHAS_POR_RESPOSTA, "resumo_objetivas": resumo_objetivas,
        "com_folhas": bool(atividade.folhas),
    })


# ---------------------------------------------------------------------------
# Folhas de resposta
# ---------------------------------------------------------------------------

@router.post("/{atividade_id}/folhas")
async def criar_folhas(request: Request, atividade_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _buscar(sessao, atividade_id)
    dados = await _formulario(request)
    quantidade = int(dados["quantidade"]) if dados.get("quantidade", "").isdigit() else 0
    linhas = int(dados["linhas"]) if dados.get("linhas", "").isdigit() else LINHAS_PADRAO
    try:
        novas = gerar_folhas(sessao, atividade, quantidade, linhas)
    except FolhasInvalidas as erro:
        return _voltar(atividade, str(erro), "#folhas")
    texto = "1 folha gerada" if len(novas) == 1 else f"{len(novas)} folhas geradas"
    return _voltar(atividade, f"{texto} (números {novas[0].numero} a {novas[-1].numero}).", "#folhas")


@router.post("/{atividade_id}/folhas/descartar")
def descartar(atividade_id: int, sessao: Session = Depends(obter_sessao)):
    atividade = _buscar(sessao, atividade_id)
    if folha_tem_respostas(atividade):
        return _voltar(atividade, "Já há respostas registradas nas folhas desta atividade, por isso elas não "
                                  "podem ser descartadas.", "#folhas")
    descartar_folhas(sessao, atividade)
    return _voltar(atividade, "Folhas descartadas. As questões podem ser alteradas de novo.", "#folhas")


@router.get("/{atividade_id}/folhas/imprimir", response_class=HTMLResponse)
def imprimir_folhas(request: Request, atividade_id: int, folha: int | None = None,
                    sessao: Session = Depends(obter_sessao)):
    """Folhas de resposta em A4, uma por aluno, com o layout de app/folhas/layout.py."""
    atividade = _buscar(sessao, atividade_id)
    folhas = [f for f in atividade.folhas if folha is None or f.id == folha]
    if not folhas:
        raise HTTPException(status_code=404, detail="Nenhuma folha de resposta gerada.")
    paginas = L.montar(atividade, atividade.linhas_por_resposta)
    return templates.TemplateResponse(request, "folhas_impressao.html", {
        "atividade": atividade, "folhas": folhas, "paginas": paginas, "L": L,
        "qr": lambda codigo, pagina: qr_svg(L.conteudo_qr(codigo, pagina)),
        "endereco": str(request.base_url).rstrip("/") + "/resultado",
    })
