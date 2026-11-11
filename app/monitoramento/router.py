"""Página de monitoramento: tempo de resposta do site, erros, serviços externos e servidor."""

import csv
import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import obter_sessao
from app.leitura import lote as lote_leitura
from app.models import Atividade, RequisicaoHttp
from app.monitoramento.resumo import LENTA_MS, PERIODOS, montar
from app.resultados import lote as lote_correcao
from app.templates_config import templates

router = APIRouter(prefix="/monitoramento", tags=["monitoramento"])


def _lotes(sessao: Session) -> list[dict]:
    """Correções e leituras em lote que estão rodando agora (ficam na memória do processo)."""
    ativos = []
    for tipo, modulo in (("Correção", lote_correcao), ("Leitura", lote_leitura)):
        for atividade_id, andamento in list(modulo._andamentos.items()):
            if andamento.em_andamento:
                atividade = sessao.get(Atividade, atividade_id)
                ativos.append({"tipo": tipo, "atividade": atividade.titulo if atividade else atividade_id,
                               "feitas": andamento.feitas + andamento.falhas, "total": andamento.total})
    return ativos


@router.get("", response_class=HTMLResponse)
def pagina(request: Request, periodo: str = "24h", sessao: Session = Depends(obter_sessao)):
    painel = montar(sessao, periodo)
    maior_total = max((i.total for i in painel.intervalos), default=0)
    maior_p95 = max((i.p95 or 0 for i in painel.intervalos), default=0)
    return templates.TemplateResponse(request, "monitoramento.html", {
        "painel": painel, "periodos": PERIODOS, "lotes": _lotes(sessao), "lenta_ms": LENTA_MS,
        "maior_total": maior_total, "maior_p95": maior_p95,
    })


@router.get("/requisicoes.csv")
def exportar(sessao: Session = Depends(obter_sessao)):
    """Todas as requisições guardadas (até 30 dias), para análise fora do sistema."""
    saida = io.StringIO()
    escritor = csv.writer(saida)
    escritor.writerow(["id", "criado_em", "metodo", "rota", "status", "duracao_ms"])
    for r in sessao.scalars(select(RequisicaoHttp).order_by(RequisicaoHttp.id)):
        escritor.writerow([r.id, r.criado_em.isoformat(), r.metodo, r.rota, r.status, r.duracao_ms])
    return StreamingResponse(iter([saida.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=requisicoes.csv"})
