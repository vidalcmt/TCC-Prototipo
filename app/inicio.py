"""Página inicial e fila de correções que esperam a decisão do professor."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import obter_sessao
from app.models import Correcao, MetricaRequisicao, Questao, RevisaoProfessor, Submissao, Usuario
from app.templates_config import templates

router = APIRouter(tags=["inicio"])


def pendentes(sessao: Session, limite: int | None = None):
    """Correções com nota sugerida e sem revisão, da mais antiga para a mais nova."""
    consulta = (
        select(Correcao, Submissao, Questao)
        .join(Submissao, Submissao.id == Correcao.submissao_id)
        .join(Questao, Questao.id == Correcao.questao_id)
        .outerjoin(RevisaoProfessor, RevisaoProfessor.correcao_id == Correcao.id)
        .where(Correcao.nota_sugerida.is_not(None), RevisaoProfessor.id.is_(None))
        .order_by(Correcao.criado_em, Correcao.id)
    )
    if limite:
        consulta = consulta.limit(limite)
    return sessao.execute(consulta).all()


def revisadas_recentes(sessao: Session, limite: int = 5):
    return sessao.execute(
        select(RevisaoProfessor, Correcao, Submissao, Questao, Usuario)
        .join(Correcao, Correcao.id == RevisaoProfessor.correcao_id)
        .join(Submissao, Submissao.id == Correcao.submissao_id)
        .join(Questao, Questao.id == Correcao.questao_id)
        .outerjoin(Usuario, Usuario.id == RevisaoProfessor.usuario_id)
        .order_by(RevisaoProfessor.criado_em.desc(), RevisaoProfessor.id.desc())
        .limit(limite)
    ).all()


def resumo_da_semana(sessao: Session) -> dict:
    desde = (datetime.now(timezone.utc) - timedelta(days=7)).replace(tzinfo=None)
    correcoes = sessao.scalars(select(Correcao).where(Correcao.criado_em >= desde)).all()
    revisoes = sessao.scalars(select(RevisaoProfessor).where(RevisaoProfessor.criado_em >= desde)).all()
    custos = sessao.scalars(
        select(MetricaRequisicao.custo_usd).where(
            MetricaRequisicao.criado_em >= desde, MetricaRequisicao.custo_usd.is_not(None)
        )
    ).all()
    diferencas = [r.nota_final - r.nota_sugerida for r in revisoes]
    return {
        "correcoes": len(correcoes),
        "revisoes": len(revisoes),
        "concordancia": sum(r.aceitou_sugestao for r in revisoes) / len(revisoes) if revisoes else None,
        "desvio": sum(diferencas) / len(diferencas) if diferencas else None,
        "custo": sum(custos),
    }


@router.get("/", response_class=HTMLResponse)
def inicio(request: Request, senha: str | None = None, sessao: Session = Depends(obter_sessao)):
    return templates.TemplateResponse(request, "inicio.html", {
        "fila": pendentes(sessao, limite=5),
        "recentes": revisadas_recentes(sessao),
        "semana": resumo_da_semana(sessao),
        "senha_trocada": senha == "trocada",
    })


@router.get("/revisar", response_class=HTMLResponse)
def para_revisar(request: Request, sessao: Session = Depends(obter_sessao)):
    return templates.TemplateResponse(request, "revisar.html", {"fila": pendentes(sessao)})
