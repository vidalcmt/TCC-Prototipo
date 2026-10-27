"""Lista de questões e páginas das objetivas: cadastro (RF01), detalhe e explicação (RF02, RF03)."""

from math import ceil
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from openai import OpenAI
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.correcao.contratos import CONTRATO_POR_PROMPT, ROTULOS_TIPO_DE_ERRO
from app.correcao.objetiva import gerar_explicacao
from app.database import obter_sessao
from app.models import Alternativa, Correcao, MetricaRequisicao, Questao, RevisaoProfessor
from app.contas.sessao import verificar_limite_diario
from app.questoes.cliente import obter_cliente_llm
from app.questoes.discursivas import pagina_da_questao
from app.templates_config import templates

router = APIRouter(prefix="/questoes", tags=["questoes"])

LETRAS = ["A", "B", "C", "D", "E"]


def buscar_questao(sessao: Session, questao_id: int) -> Questao:
    questao = sessao.get(Questao, questao_id)
    if questao is None:
        raise HTTPException(status_code=404, detail="Questão não encontrada")
    return questao


POR_PAGINA = 50
FILTROS = ("busca", "numero", "tipo", "area", "fonte", "ano", "situacao")
SITUACOES = {"": "Todas", "pendente": "Com correção para revisar", "sem_correcao": "Ainda sem correção"}


def _filtrar(consulta, f: dict[str, str]):
    """Aplica à consulta de questões os filtros preenchidos na lista."""
    if f["busca"]:
        consulta = consulta.where(Questao.enunciado.ilike(f"%{f['busca']}%"))
    if f["numero"].isdigit():
        consulta = consulta.where(Questao.id == int(f["numero"]))
    if f["tipo"] in ("objetiva", "discursiva"):
        consulta = consulta.where(Questao.tipo == f["tipo"])
    if f["area"]:
        consulta = consulta.where(Questao.area == f["area"])
    if f["fonte"]:
        consulta = consulta.where(Questao.fonte == f["fonte"])
    if f["ano"].isdigit():
        consulta = consulta.where(Questao.ano == int(f["ano"]))
    if f["situacao"] == "pendente":
        sem_revisao = ~exists().where(RevisaoProfessor.correcao_id == Correcao.id)
        consulta = consulta.where(exists().where(
            Correcao.questao_id == Questao.id, Correcao.nota_sugerida.is_not(None), sem_revisao))
    elif f["situacao"] == "sem_correcao":
        consulta = consulta.where(~exists().where(Correcao.questao_id == Questao.id))
    return consulta


def _valores(sessao: Session, coluna) -> list:
    return [v for v in sessao.scalars(select(coluna).distinct().where(coluna.is_not(None)).order_by(coluna))]


@router.get("", response_class=HTMLResponse)
def listar(request: Request, pagina: int = 1, sessao: Session = Depends(obter_sessao)):
    """Todas as questões, 50 por página, com filtros que se mantêm ao trocar de página."""
    filtros = {nome: (request.query_params.get(nome) or "").strip() for nome in FILTROS}
    total = sessao.scalar(_filtrar(select(func.count(Questao.id)), filtros))
    paginas = max(1, ceil(total / POR_PAGINA))
    pagina = min(max(1, pagina), paginas)

    total_correcoes = (
        select(Correcao.questao_id, func.count().label("n")).group_by(Correcao.questao_id).subquery()
    )
    linhas = sessao.execute(
        _filtrar(select(Questao, func.coalesce(total_correcoes.c.n, 0)), filtros)
        .outerjoin(total_correcoes, total_correcoes.c.questao_id == Questao.id)
        .order_by(Questao.id)
        .limit(POR_PAGINA).offset((pagina - 1) * POR_PAGINA)
    ).all()

    ativos = {nome: valor for nome, valor in filtros.items() if valor}

    def link_pagina(numero: int) -> str:
        return "/questoes?" + urlencode({**ativos, "pagina": numero})

    return templates.TemplateResponse(request, "questoes_lista.html", {
        "linhas": linhas, "filtros": filtros, "filtrando": bool(ativos),
        "total": total, "pagina": pagina, "paginas": paginas, "link_pagina": link_pagina,
        "primeira": (pagina - 1) * POR_PAGINA + 1 if total else 0,
        "ultima": min(pagina * POR_PAGINA, total),
        "opcoes": {
            "area": _valores(sessao, Questao.area),
            "fonte": _valores(sessao, Questao.fonte),
            "ano": _valores(sessao, Questao.ano),
        },
        "situacoes": SITUACOES,
    })


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
    if questao.tipo == "discursiva":
        return pagina_da_questao(request, questao, sessao)
    correcoes = sessao.scalars(
        select(Correcao).where(Correcao.questao_id == questao.id).order_by(Correcao.id.desc())
    ).all()

    explicacao, metrica = None, None
    if correcoes:
        # Cada correção é lida com o contrato da versão de prompt que a gerou.
        contrato = CONTRATO_POR_PROMPT[correcoes[0].prompt_versao]
        explicacao = contrato.model_validate_json(correcoes[0].feedback_json)
        metrica = sessao.scalars(
            select(MetricaRequisicao).where(MetricaRequisicao.correcao_id == correcoes[0].id)
        ).first()

    return templates.TemplateResponse(request, "questao_detalhe.html", {
        "questao": questao,
        "explicacao": explicacao,
        "por_letra": {e.letra: e for e in explicacao.explicacoes} if explicacao else {},
        "metrica": metrica,
        "rotulos_erro": ROTULOS_TIPO_DE_ERRO,
        "total_explicacoes": len(correcoes),
        "falha": sessao.get(MetricaRequisicao, falha) if falha else None,
    })


@router.post("/{questao_id}/explicar")
def explicar(request: Request, questao_id: int, sessao: Session = Depends(obter_sessao),
             cliente: OpenAI | None = Depends(obter_cliente_llm)):
    questao = buscar_questao(sessao, questao_id)
    if questao.tipo != "objetiva":
        raise HTTPException(status_code=400, detail="Explicação de alternativas só existe em questões objetivas.")
    usuario = request.state.usuario
    verificar_limite_diario(sessao, usuario)
    resultado = gerar_explicacao(sessao, questao, cliente=cliente, usuario_id=usuario.id)
    if resultado.sucesso:
        return RedirectResponse(f"/questoes/{questao_id}", status_code=303)
    return RedirectResponse(
        f"/questoes/{questao_id}?falha={resultado.metrica.id}", status_code=303
    )
