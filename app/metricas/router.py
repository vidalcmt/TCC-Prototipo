"""Consulta e exportação das métricas e das revisões (RF12 e RF14)."""

import csv
import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import obter_sessao
from app.metricas.resumo import linhas_de_revisao, resumo_concordancia, resumo_requisicoes
from app.models import MetricaRequisicao, Questao, Submissao, Usuario
from app.templates_config import templates

router = APIRouter(prefix="/metricas", tags=["metricas"])

COLUNAS = [
    "id", "criado_em", "usuario_id", "questao_id", "submissao_id", "correcao_id", "tipo_questao",
    "usou_resposta_esperada",
    "modelo_solicitado", "modelo", "prompt_versao", "tokens_entrada",
    "tokens_entrada_cache", "tokens_escrita_cache", "tokens_saida",
    "tokens_raciocinio", "custo_usd", "latencia_ms", "sucesso", "motivo_falha",
]


LIMITE_LINHAS = 200


def _por_id(sessao: Session, modelo, ids: set[int]) -> dict:
    if not ids:
        return {}
    return {obj.id: obj for obj in sessao.scalars(select(modelo).where(modelo.id.in_(ids)))}


@router.get("", response_class=HTMLResponse)
def listar(request: Request, questao: int | None = None, resposta: int | None = None,
           sessao: Session = Depends(obter_sessao)):
    """Resumo e últimas chamadas. Com ?questao= ou ?resposta=, mostra só as chamadas daquela origem."""
    consulta = select(MetricaRequisicao).order_by(MetricaRequisicao.id.desc()).limit(LIMITE_LINHAS)
    if questao is not None:
        consulta = consulta.where(MetricaRequisicao.questao_id == questao)
    if resposta is not None:
        consulta = consulta.where(MetricaRequisicao.submissao_id == resposta)
    metricas = sessao.scalars(consulta).all()

    filtrando = questao is not None or resposta is not None
    custo_filtrado = sum(m.custo_usd or 0 for m in metricas) if filtrando else None
    return templates.TemplateResponse(request, "metricas.html", {
        "metricas": metricas,
        "requisicoes": resumo_requisicoes(sessao),
        "concordancia": resumo_concordancia(sessao),
        "questoes": _por_id(sessao, Questao, {m.questao_id for m in metricas if m.questao_id}),
        "respostas": _por_id(sessao, Submissao, {m.submissao_id for m in metricas if m.submissao_id}),
        "usuarios": _por_id(sessao, Usuario, {m.usuario_id for m in metricas if m.usuario_id}),
        "filtro_questao": questao, "filtro_resposta": resposta, "custo_filtrado": custo_filtrado,
        "limite": LIMITE_LINHAS,
    })


def _csv(cabecalho: list[str], linhas, nome_arquivo: str) -> StreamingResponse:
    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


@router.get("/exportar.csv")
def exportar_csv(sessao: Session = Depends(obter_sessao)):
    metricas = sessao.scalars(select(MetricaRequisicao).order_by(MetricaRequisicao.id))
    return _csv(COLUNAS, ([getattr(m, c) for c in COLUNAS] for m in metricas), "metricas.csv")


COLUNAS_REVISOES = [
    "revisao_id", "criado_em", "avaliador_id", "correcao_id", "resposta_id", "codigo_corpus", "origem",
    "questao_id", "usou_resposta_esperada", "prompt_versao", "modelo", "nota_maxima",
    "nota_sugerida", "nota_final", "aceitou_sugestao", "diferenca", "comentario",
]


@router.get("/revisoes.csv")
def exportar_revisoes(sessao: Session = Depends(obter_sessao)):
    """Uma linha por revisão do professor: a base da taxa de concordância e do desvio."""
    linhas = (
        [r.id, r.criado_em, r.usuario_id, c.id, s.id, s.codigo_corpus, s.origem, q.id, c.usou_resposta_esperada,
         c.prompt_versao, c.modelo, q.nota_maxima, r.nota_sugerida, r.nota_final, r.aceitou_sugestao,
         r.nota_final - r.nota_sugerida, r.comentario]
        for r, c, s, q in linhas_de_revisao(sessao)
    )
    return _csv(COLUNAS_REVISOES, linhas, "revisoes.csv")
