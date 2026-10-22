"""Páginas de questões discursivas: cadastro (RF04), respostas (RF05) e correção (RF06 a RF08)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from openai import OpenAI
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.correcao.contratos import CONTRATO_POR_PROMPT
from app.correcao.discursiva import CondicaoIndisponivel, gerar_correcao
from app.database import obter_sessao
from app.models import (
    Correcao, CriterioRubrica, MetricaRequisicao, Questao, RespostaEsperada, RevisaoProfessor, Submissao,
)
from app.questoes.cliente import obter_cliente_llm
from app.templates_config import templates

router = APIRouter(tags=["discursivas"])

LINHAS_RUBRICA = 6
ORIGENS = {"": "Não informada", "autor": "Autor", "voluntario": "Voluntário", "especialista": "Especialista"}
ROTULOS_STATUS = {"atendido": "Atendido", "parcial": "Parcial", "nao_atendido": "Não atendido"}


def _numero(texto: str | None) -> float | None:
    """Lê números digitados com vírgula ou ponto. Devolve None se não for número."""
    if texto is None or not texto.strip():
        return None
    try:
        return float(texto.strip().replace(",", "."))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Cadastro da questão (RF04)
# ---------------------------------------------------------------------------

@router.get("/questoes/nova-discursiva", response_class=HTMLResponse)
def formulario(request: Request):
    return templates.TemplateResponse(request, "discursiva_nova.html", {
        "dados": {"nota_maxima": "10"}, "erros": [], "linhas": range(1, LINHAS_RUBRICA + 1),
    })


@router.post("/questoes/discursivas", response_class=HTMLResponse)
async def cadastrar(request: Request, sessao: Session = Depends(obter_sessao)):
    dados = {chave: str(valor).strip() for chave, valor in (await request.form()).items()}

    erros = []
    if not dados.get("enunciado"):
        erros.append("Preencha o enunciado.")
    nota_maxima = _numero(dados.get("nota_maxima"))
    if nota_maxima is None or nota_maxima <= 0:
        erros.append("Informe uma nota máxima maior que zero.")

    criterios = []
    for i in range(1, LINHAS_RUBRICA + 1):
        descricao, peso_texto = dados.get(f"criterio_{i}", ""), dados.get(f"peso_{i}", "")
        if not descricao and not peso_texto:
            continue
        peso = _numero(peso_texto)
        if not descricao:
            erros.append(f"Critério {i}: falta a descrição.")
        elif peso is None or peso <= 0:
            erros.append(f"Critério {i}: informe um peso maior que zero.")
        else:
            criterios.append(CriterioRubrica(descricao=descricao, peso=peso))

    if erros:
        return templates.TemplateResponse(request, "discursiva_nova.html", {
            "dados": dados, "erros": erros, "linhas": range(1, LINHAS_RUBRICA + 1),
        }, status_code=400)

    ano = dados.get("ano", "")
    questao = Questao(
        tipo="discursiva",
        enunciado=dados["enunciado"],
        area=dados.get("area") or None,
        fonte=dados.get("fonte") or "Cadastro manual",
        ano=int(ano) if ano.isdigit() else None,
        nota_maxima=nota_maxima,
        criterios=criterios,
    )
    if dados.get("resposta_esperada"):
        questao.resposta_esperada = RespostaEsperada(texto=dados["resposta_esperada"])
    sessao.add(questao)
    sessao.commit()
    return RedirectResponse(f"/questoes/{questao.id}", status_code=303)


def pagina_da_questao(request: Request, questao: Questao, sessao: Session) -> HTMLResponse:
    """Página de uma questão discursiva; chamada pela rota de detalhe de questões."""
    totais = (
        select(
            Correcao.submissao_id,
            func.count(Correcao.id).label("correcoes"),
            func.count(RevisaoProfessor.id).label("revisadas"),
        )
        .outerjoin(RevisaoProfessor, RevisaoProfessor.correcao_id == Correcao.id)
        .group_by(Correcao.submissao_id)
        .subquery()
    )
    respostas = sessao.execute(
        select(Submissao, func.coalesce(totais.c.correcoes, 0), func.coalesce(totais.c.revisadas, 0))
        .outerjoin(totais, totais.c.submissao_id == Submissao.id)
        .where(Submissao.questao_id == questao.id)
        .order_by(Submissao.id)
    ).all()
    return templates.TemplateResponse(request, "discursiva_questao.html", {
        "questao": questao, "respostas": respostas, "origens": ORIGENS,
    })


# ---------------------------------------------------------------------------
# Respostas (RF05) e correção (RF06 a RF08)
# ---------------------------------------------------------------------------

def _questao_discursiva(sessao: Session, questao_id: int) -> Questao:
    questao = sessao.get(Questao, questao_id)
    if questao is None or questao.tipo != "discursiva":
        raise HTTPException(status_code=404, detail="Questão discursiva não encontrada")
    return questao


def _submissao(sessao: Session, resposta_id: int) -> Submissao:
    submissao = sessao.get(Submissao, resposta_id)
    if submissao is None:
        raise HTTPException(status_code=404, detail="Resposta não encontrada")
    return submissao


@router.post("/questoes/{questao_id}/respostas", response_class=HTMLResponse)
async def registrar_resposta(request: Request, questao_id: int, sessao: Session = Depends(obter_sessao)):
    questao = _questao_discursiva(sessao, questao_id)
    dados = {chave: str(valor).strip() for chave, valor in (await request.form()).items()}
    if not dados.get("resposta_aluno"):
        raise HTTPException(status_code=400, detail="A resposta do aluno está vazia.")
    origem = dados.get("origem", "")
    submissao = Submissao(
        questao_id=questao.id,
        resposta_aluno=dados["resposta_aluno"],
        codigo_corpus=dados.get("codigo_corpus") or None,
        origem=origem if origem in ORIGENS and origem else None,
    )
    sessao.add(submissao)
    sessao.commit()
    return RedirectResponse(f"/respostas/{submissao.id}", status_code=303)


@router.get("/respostas/{resposta_id}", response_class=HTMLResponse)
def pagina_da_resposta(request: Request, resposta_id: int, falha: int | None = None,
                       erro_revisao: int | None = None, mensagem: str | None = None,
                       sessao: Session = Depends(obter_sessao)):
    submissao = _submissao(sessao, resposta_id)
    questao = sessao.get(Questao, submissao.questao_id)

    correcoes = []
    for c in sessao.scalars(
        select(Correcao).where(Correcao.submissao_id == submissao.id).order_by(Correcao.id.desc())
    ):
        analise = CONTRATO_POR_PROMPT[c.prompt_versao].model_validate_json(c.feedback_json)
        metrica = sessao.scalars(
            select(MetricaRequisicao).where(MetricaRequisicao.correcao_id == c.id)
        ).first()
        revisao = sessao.scalars(
            select(RevisaoProfessor).where(RevisaoProfessor.correcao_id == c.id)
        ).first()
        correcoes.append({
            "correcao": c, "analise": analise, "metrica": metrica, "revisao": revisao,
            "erro": mensagem if erro_revisao == c.id else None,
        })

    return templates.TemplateResponse(request, "resposta.html", {
        "submissao": submissao, "questao": questao, "correcoes": correcoes,
        "origens": ORIGENS, "rotulos_status": ROTULOS_STATUS,
        "falha": sessao.get(MetricaRequisicao, falha) if falha else None,
    })


@router.post("/respostas/{resposta_id}/corrigir")
async def corrigir(request: Request, resposta_id: int, sessao: Session = Depends(obter_sessao),
                   cliente: OpenAI | None = Depends(obter_cliente_llm)):
    submissao = _submissao(sessao, resposta_id)
    condicao = (await request.form()).get("condicao")
    if condicao not in ("com", "sem"):
        raise HTTPException(status_code=400, detail="Condição deve ser 'com' ou 'sem'.")
    try:
        resultado = gerar_correcao(sessao, submissao, condicao == "com", cliente=cliente)
    except CondicaoIndisponivel as erro:
        raise HTTPException(status_code=400, detail=str(erro))
    if resultado.sucesso:
        return RedirectResponse(f"/respostas/{resposta_id}", status_code=303)
    return RedirectResponse(f"/respostas/{resposta_id}?falha={resultado.metrica.id}", status_code=303)
