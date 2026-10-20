"""Páginas de questões objetivas: lista, cadastro (RF01), detalhe e explicação (RF02, RF03)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from openai import OpenAI
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.correcao.contratos import CorrecaoObjetiva
from app.correcao.objetiva import gerar_explicacao
from app.database import obter_sessao
from app.models import Alternativa, Correcao, MetricaRequisicao, Questao
from app.templates_config import templates

router = APIRouter(prefix="/questoes", tags=["questoes"])

LETRAS = ["A", "B", "C", "D", "E"]


def obter_cliente_llm() -> OpenAI | None:
    """Cliente do modelo. None significa o cliente padrão; os testes trocam por um falso."""
    return None


def buscar_questao(sessao: Session, questao_id: int) -> Questao:
    questao = sessao.get(Questao, questao_id)
    if questao is None:
        raise HTTPException(status_code=404, detail="Questão não encontrada")
    return questao


@router.get("", response_class=HTMLResponse)
def listar(request: Request, sessao: Session = Depends(obter_sessao)):
    total_explicacoes = (
        select(Correcao.questao_id, func.count().label("n")).group_by(Correcao.questao_id).subquery()
    )
    linhas = sessao.execute(
        select(Questao, func.coalesce(total_explicacoes.c.n, 0))
        .outerjoin(total_explicacoes, total_explicacoes.c.questao_id == Questao.id)
        .where(Questao.tipo == "objetiva")
        .order_by(Questao.id)
    ).all()
    return templates.TemplateResponse(request, "questoes_lista.html", {"linhas": linhas})


@router.get("/nova", response_class=HTMLResponse)
def formulario(request: Request):
    return templates.TemplateResponse(
        request, "questao_nova.html", {"letras": LETRAS, "dados": {}, "erros": []}
    )


@router.post("", response_class=HTMLResponse)
async def cadastrar(request: Request, sessao: Session = Depends(obter_sessao)):
    formulario = await request.form()
    dados = {chave: str(valor).strip() for chave, valor in formulario.items()}

    erros = []
    if not dados.get("enunciado"):
        erros.append("Preencha o enunciado.")
    faltando = [l for l in LETRAS if not dados.get(f"alternativa_{l}")]
    if faltando:
        erros.append(f"Preencha as alternativas: {', '.join(faltando)}.")
    if dados.get("correta") not in LETRAS:
        erros.append("Indique qual alternativa é a correta.")
    if erros:
        return templates.TemplateResponse(
            request, "questao_nova.html",
            {"letras": LETRAS, "dados": dados, "erros": erros}, status_code=400,
        )

    ano = dados.get("ano")
    questao = Questao(
        tipo="objetiva",
        enunciado=dados["enunciado"],
        area=dados.get("area") or None,
        fonte=dados.get("fonte") or "Cadastro manual",
        ano=int(ano) if ano and ano.isdigit() else None,
        alternativas=[
            Alternativa(letra=l, texto=dados[f"alternativa_{l}"], correta=l == dados["correta"])
            for l in LETRAS
        ],
    )
    sessao.add(questao)
    sessao.commit()
    return RedirectResponse(f"/questoes/{questao.id}", status_code=303)


@router.get("/{questao_id}", response_class=HTMLResponse)
def detalhe(request: Request, questao_id: int, falha: int | None = None,
            sessao: Session = Depends(obter_sessao)):
    questao = buscar_questao(sessao, questao_id)
    correcoes = sessao.scalars(
        select(Correcao).where(Correcao.questao_id == questao.id).order_by(Correcao.id.desc())
    ).all()

    explicacao, metrica = None, None
    if correcoes:
        explicacao = CorrecaoObjetiva.model_validate_json(correcoes[0].feedback_json)
        metrica = sessao.scalars(
            select(MetricaRequisicao).where(MetricaRequisicao.correcao_id == correcoes[0].id)
        ).first()

    return templates.TemplateResponse(request, "questao_detalhe.html", {
        "questao": questao,
        "explicacao": explicacao,
        "por_letra": {e.letra: e for e in explicacao.explicacoes} if explicacao else {},
        "metrica": metrica,
        "total_explicacoes": len(correcoes),
        "falha": sessao.get(MetricaRequisicao, falha) if falha else None,
    })


@router.post("/{questao_id}/explicar")
def explicar(questao_id: int, sessao: Session = Depends(obter_sessao),
             cliente: OpenAI | None = Depends(obter_cliente_llm)):
    questao = buscar_questao(sessao, questao_id)
    resultado = gerar_explicacao(sessao, questao, cliente=cliente)
    if resultado.sucesso:
        return RedirectResponse(f"/questoes/{questao_id}", status_code=303)
    return RedirectResponse(
        f"/questoes/{questao_id}?falha={resultado.metrica.id}", status_code=303
    )
