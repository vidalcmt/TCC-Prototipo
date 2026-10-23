"""Revisão da nota sugerida pelo professor (RF09, RF10 e RF11).

A nota final só passa a existir quando o professor aceita a sugestão ou
informa outra. As duas notas ficam gravadas lado a lado, o que permite
calcular a concordância entre o modelo e o professor.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Correcao, Questao, RevisaoProfessor

TOLERANCIA = 1e-9


class RevisaoInvalida(ValueError):
    pass


def revisao_da(sessao: Session, correcao_id: int) -> RevisaoProfessor | None:
    return sessao.scalars(
        select(RevisaoProfessor).where(RevisaoProfessor.correcao_id == correcao_id)
    ).first()


def registrar_revisao(
    sessao: Session, correcao: Correcao, nota_final: float, comentario: str | None = None,
    usuario_id: int | None = None,
) -> RevisaoProfessor:
    """Grava a decisão do professor sobre uma correção.

    aceitou_sugestao é calculado aqui, comparando as notas, e não informado
    pela tela: assim, digitar a mesma nota sugerida também conta como aceite.
    """
    if correcao.nota_sugerida is None:
        raise RevisaoInvalida("Esta correção não tem nota sugerida para revisar.")
    if revisao_da(sessao, correcao.id) is not None:
        raise RevisaoInvalida("Esta correção já foi revisada. A decisão registrada não é alterada.")

    nota_maxima = sessao.get(Questao, correcao.questao_id).nota_maxima
    if not 0 <= nota_final <= nota_maxima + TOLERANCIA:
        raise RevisaoInvalida(f"A nota final deve estar entre 0 e {nota_maxima:g}.")

    revisao = RevisaoProfessor(
        correcao_id=correcao.id,
        usuario_id=usuario_id,
        nota_sugerida=correcao.nota_sugerida,
        nota_final=nota_final,
        aceitou_sugestao=abs(nota_final - correcao.nota_sugerida) <= TOLERANCIA,
        comentario=(comentario or "").strip() or None,
    )
    sessao.add(revisao)
    try:
        sessao.commit()
    except IntegrityError:
        # Dois envios quase simultâneos (por exemplo, clique duplo): o banco
        # aceita só o primeiro, pela restrição de uma revisão por correção.
        sessao.rollback()
        raise RevisaoInvalida("Esta correção já foi revisada. A decisão registrada não é alterada.")
    return revisao
