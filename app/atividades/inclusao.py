"""Criar uma questão de dentro de uma atividade.

O professor monta a atividade e, quando a questão que ele quer ainda não está
cadastrada, cria a questão ali mesmo: o formulário de cadastro abre com a
atividade de destino, e a questão criada entra no fim da atividade.
"""

from urllib.parse import quote

from sqlalchemy.orm import Session

from app.folhas.servico import questoes_travadas
from app.models import Atividade, AtividadeQuestao, Questao


def atividade_de_destino(sessao: Session, valor) -> Atividade | None:
    """A atividade indicada no formulário, ou None se não houver ou não existir."""
    texto = str(valor or "").strip()
    return sessao.get(Atividade, int(texto)) if texto.isdigit() else None


def destino_depois_de_criar(sessao: Session, questao: Questao, atividade: Atividade | None) -> str:
    """Inclui a questão na atividade, quando há uma, e devolve para onde ir depois do cadastro."""
    if atividade is None:
        return f"/questoes/{questao.id}"
    if questoes_travadas(atividade):
        aviso = ("A questão foi cadastrada, mas não entrou na atividade: as questões estão travadas porque as "
                 "folhas de resposta já foram geradas.")
    else:
        atividade.itens.append(AtividadeQuestao(questao_id=questao.id, ordem=len(atividade.itens) + 1))
        sessao.commit()
        aviso = f"Questão cadastrada e incluída na atividade como questão {len(atividade.itens)}."
    return f"/atividades/{atividade.id}?aviso={quote(aviso)}#questoes"
