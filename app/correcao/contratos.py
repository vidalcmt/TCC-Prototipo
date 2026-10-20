"""Contratos de saída do modelo, conforme a seção "Contrato de saída da IA" da especificação.

A API recebe estas classes como formato obrigatório da resposta (saída
estruturada). As descrições dos campos vão junto e orientam o modelo.

Campo com razão metodológica, que não deve ser removido:
- conceito_envolvido: permite agrupar erros por conceito na análise.
"""

from typing import Literal

from pydantic import BaseModel, Field

Letra = Literal["A", "B", "C", "D", "E"]


class ExplicacaoAlternativa(BaseModel):
    letra: Letra
    correta: bool = Field(description="Verdadeiro apenas para a alternativa indicada como correta.")
    por_que: str = Field(
        description=(
            "Para alternativa incorreta: o erro de raciocínio que leva um estudante a escolhê-la "
            "e por que ele não se sustenta. Para a correta: por que ela é a mais adequada."
        )
    )
    conceito_envolvido: str = Field(
        description="Conceito central mobilizado pela alternativa, em 2 a 6 palavras."
    )


class CorrecaoObjetiva(BaseModel):
    questao_id: str
    alternativa_correta: Letra
    explicacoes: list[ExplicacaoAlternativa] = Field(
        description="Uma explicação por alternativa, em ordem alfabética, de A até a última."
    )
    explicacao_correta: str = Field(
        description="O caminho de raciocínio, passo a passo, do enunciado até a resposta correta."
    )
    nivel_dificuldade_estimado: Literal["baixo", "medio", "alto"]


def problemas_de_consistencia(
    saida: CorrecaoObjetiva, questao_id: int, letras: list[str], gabarito: str
) -> list[str]:
    """Confere a saída com a questão cadastrada. Lista vazia significa saída consistente.

    O formato já foi garantido pela API; aqui se verifica o conteúdo: a resposta
    não pode contrariar o gabarito informado pelo professor nem pular ou repetir
    alternativas.
    """
    problemas = []
    if saida.questao_id != str(questao_id):
        problemas.append(f"questao_id {saida.questao_id!r} diferente de {questao_id}")
    if saida.alternativa_correta != gabarito:
        problemas.append(f"alternativa_correta {saida.alternativa_correta} diferente do gabarito {gabarito}")

    recebidas = [e.letra for e in saida.explicacoes]
    if sorted(recebidas) != sorted(letras):
        problemas.append(f"alternativas explicadas {recebidas} diferentes das cadastradas {letras}")

    marcadas = [e.letra for e in saida.explicacoes if e.correta]
    if marcadas != [gabarito]:
        problemas.append(f"alternativas marcadas como corretas {marcadas}, esperado [{gabarito}]")
    return problemas
