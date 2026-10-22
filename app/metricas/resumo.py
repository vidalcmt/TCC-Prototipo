"""Números do artigo calculados a partir do banco.

Correspondem à tabela "Disso saem direto os números do artigo" da
especificação: custo e tempo médios por tipo, taxa de falha, concordância
entre modelo e professor, desvio médio da nota e efeito da resposta esperada.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Correcao, MetricaRequisicao, Questao, RevisaoProfessor, Submissao


@dataclass
class ResumoRequisicoes:
    grupo: str
    total: int
    falhas: int
    custo_medio: float | None
    latencia_media_ms: float | None

    @property
    def taxa_falha(self) -> float | None:
        return self.falhas / self.total if self.total else None


@dataclass
class ResumoConcordancia:
    grupo: str
    revisoes: int
    aceitas: int
    desvio_medio: float | None
    desvio_absoluto_medio: float | None

    @property
    def taxa_concordancia(self) -> float | None:
        return self.aceitas / self.revisoes if self.revisoes else None


def _media(valores: list[float]) -> float | None:
    return sum(valores) / len(valores) if valores else None


def resumo_requisicoes(sessao: Session) -> list[ResumoRequisicoes]:
    metricas = sessao.scalars(select(MetricaRequisicao)).all()
    grupos = [("Objetivas", "objetiva"), ("Discursivas", "discursiva")]
    resultado = []
    for rotulo, tipo in grupos:
        ms = [m for m in metricas if m.tipo_questao == tipo]
        resultado.append(ResumoRequisicoes(
            grupo=rotulo,
            total=len(ms),
            falhas=sum(1 for m in ms if not m.sucesso),
            custo_medio=_media([m.custo_usd for m in ms if m.custo_usd is not None]),
            latencia_media_ms=_media([m.latencia_ms for m in ms if m.sucesso]),
        ))
    return resultado


def linhas_de_revisao(sessao: Session):
    """Cada revisão com os dados da correção, da resposta e da questão."""
    return sessao.execute(
        select(RevisaoProfessor, Correcao, Submissao, Questao)
        .join(Correcao, Correcao.id == RevisaoProfessor.correcao_id)
        .join(Submissao, Submissao.id == Correcao.submissao_id)
        .join(Questao, Questao.id == Correcao.questao_id)
        .order_by(RevisaoProfessor.id)
    ).all()


def resumo_concordancia(sessao: Session) -> list[ResumoConcordancia]:
    linhas = linhas_de_revisao(sessao)
    grupos = [
        ("Todas", lambda c: True),
        ("Sem resposta esperada", lambda c: c.usou_resposta_esperada is False),
        ("Com resposta esperada", lambda c: c.usou_resposta_esperada is True),
    ]
    resultado = []
    for rotulo, filtro in grupos:
        rs = [r for r, c, _, _ in linhas if filtro(c)]
        diferencas = [r.nota_final - r.nota_sugerida for r in rs]
        resultado.append(ResumoConcordancia(
            grupo=rotulo,
            revisoes=len(rs),
            aceitas=sum(1 for r in rs if r.aceitou_sugestao),
            desvio_medio=_media(diferencas),
            desvio_absoluto_medio=_media([abs(d) for d in diferencas]),
        ))
    return resultado
