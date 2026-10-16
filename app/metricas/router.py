"""Consulta e exportação das métricas (RF12 e RF14)."""

import csv
import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import obter_sessao
from app.models import MetricaRequisicao
from app.templates_config import templates

router = APIRouter(prefix="/metricas", tags=["metricas"])

COLUNAS = [
    "id", "criado_em", "correcao_id", "tipo_questao", "usou_resposta_esperada",
    "modelo_solicitado", "modelo", "prompt_versao", "tokens_entrada",
    "tokens_entrada_cache", "tokens_escrita_cache", "tokens_saida",
    "tokens_raciocinio", "custo_usd", "latencia_ms", "sucesso", "motivo_falha",
]


@router.get("", response_class=HTMLResponse)
def listar(request: Request, sessao: Session = Depends(obter_sessao)):
    metricas = sessao.scalars(
        select(MetricaRequisicao).order_by(MetricaRequisicao.id.desc()).limit(200)
    ).all()
    return templates.TemplateResponse(request, "metricas.html", {"metricas": metricas})


@router.get("/exportar.csv")
def exportar_csv(sessao: Session = Depends(obter_sessao)):
    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(COLUNAS)
    for m in sessao.scalars(select(MetricaRequisicao).order_by(MetricaRequisicao.id)):
        escritor.writerow([getattr(m, coluna) for coluna in COLUNAS])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=metricas.csv"},
    )
