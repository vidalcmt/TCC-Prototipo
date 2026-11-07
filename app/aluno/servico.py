"""O que o aluno vê do próprio resultado.

Só a parte escrita para o aluno sai daqui: nas discursivas, o feedback
elaborado e a nota confirmada pelo professor; nas objetivas, a alternativa
marcada, a correta e a explicação gerada para elas. A análise por critério,
escrita para o professor, a nota sugerida pelo modelo e os comentários da
revisão nunca são mostrados.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.correcao.contratos import CONTRATO_POR_PROMPT
from app.models import Correcao, Folha, Questao
from app.resultados.servico import (
    ANULADA, CERTA, EM_BRANCO, ERRADA, MARCACAO_MULTIPLA, REVISADA, ResultadoFolha, resultado_da_folha,
    visivel_para_o_aluno,
)


@dataclass
class ExplicacaoObjetiva:
    marcada: str | None       # por que a alternativa marcada está errada
    correta: str | None       # como chegar à resposta correta
    pista: str | None         # pista do enunciado (prompt v3)


@dataclass
class QuestaoDoAluno:
    numero: int
    tipo: str
    situacao: str
    pontos: float
    valor: float
    marcada: str | None = None
    gabarito: str | None = None
    explicacao: ExplicacaoObjetiva | None = None
    feedback: str | None = None


def buscar_folha(sessao: Session, codigo: str) -> Folha | None:
    return sessao.scalars(select(Folha).where(Folha.codigo == codigo)).first()


def _texto(explicacao) -> str:
    # v3 tem um campo único; v1 e v2 explicam em por_que
    return getattr(explicacao, "explicacao", None) or getattr(explicacao, "por_que", "")


def explicacao_objetiva(sessao: Session, questao: Questao, marcada: str | None) -> ExplicacaoObjetiva | None:
    """Explicação mais recente da questão, gerada pelo professor na página da questão."""
    correcao = sessao.scalars(
        select(Correcao).where(Correcao.questao_id == questao.id, Correcao.submissao_id.is_(None))
        .order_by(Correcao.id.desc())
    ).first()
    if correcao is None or correcao.prompt_versao not in CONTRATO_POR_PROMPT:
        return None
    saida = CONTRATO_POR_PROMPT[correcao.prompt_versao].model_validate_json(correcao.feedback_json)
    por_letra = {e.letra: e for e in saida.explicacoes}
    certa = por_letra.get(saida.alternativa_correta)
    errada = por_letra.get(marcada) if marcada and marcada != saida.alternativa_correta else None
    return ExplicacaoObjetiva(
        marcada=_texto(errada) if errada else None,
        # v2 e v3 têm o caminho de raciocínio até a resposta; v1 só a explicação da alternativa
        correta=getattr(saida, "explicacao_correta", None) or (_texto(certa) if certa else None),
        pista=getattr(saida, "pista_do_enunciado", None),
    )


def resultado_para_o_aluno(sessao: Session, folha: Folha) -> tuple[ResultadoFolha, list[QuestaoDoAluno]] | None:
    """None enquanto o resultado não pode ser mostrado ao aluno."""
    resultado = resultado_da_folha(sessao, folha)
    if not visivel_para_o_aluno(resultado):
        return None
    questoes = []
    for linha in resultado.linhas:
        item = QuestaoDoAluno(linha.numero, linha.questao.tipo, linha.situacao, linha.pontos, linha.valor)
        if linha.questao.tipo == "objetiva":
            marcada = linha.submissao.alternativa_escolhida if linha.submissao else None
            item.marcada = None if marcada == MARCACAO_MULTIPLA else marcada
            item.gabarito = linha.gabarito
            if linha.situacao in (ERRADA, EM_BRANCO, ANULADA, CERTA):
                item.explicacao = explicacao_objetiva(sessao, linha.questao, item.marcada)
        elif linha.situacao == REVISADA:
            saida = CONTRATO_POR_PROMPT[linha.correcao.prompt_versao].model_validate_json(linha.correcao.feedback_json)
            item.feedback = saida.feedback_elaborado
        questoes.append(item)
    return resultado, questoes
