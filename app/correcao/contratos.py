"""Contratos de saída do modelo, conforme a seção "Contrato de saída da IA" da especificação.

A API recebe estas classes como formato obrigatório da resposta (saída
estruturada). As descrições dos campos vão junto e orientam o modelo.

Cada versão de prompt tem o seu contrato (CONTRATO_POR_PROMPT). Versões
antigas continuam aqui para que as correções já gravadas possam ser lidas.

Campos com razão metodológica, que não devem ser removidos:
- conceito_envolvido: permite agrupar erros por conceito na análise;
- tipo_de_erro (v2): permite contar quais tipos de erro os distratores exploram.
"""

from typing import Literal

from pydantic import BaseModel, Field

Letra = Literal["A", "B", "C", "D", "E"]
Dificuldade = Literal["baixo", "medio", "alto"]


# ---------------------------------------------------------------------------
# Versão 1 (prompt objetiva_v1)
# ---------------------------------------------------------------------------

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
    nivel_dificuldade_estimado: Dificuldade


# ---------------------------------------------------------------------------
# Versão 2 (prompt objetiva_v2): tipo de erro, elemento errado e como verificar
# ---------------------------------------------------------------------------

TipoDeErro = Literal[
    "anacronismo",
    "contexto_historico",
    "conceito_trocado",
    "leitura_parcial",
    "extrapolacao",
    "causa_efeito",
    "fato_incorreto",
    "nao_responde",
    "outro",
]

ROTULOS_TIPO_DE_ERRO: dict[str, str] = {
    "anacronismo": "Época ou data errada",
    "contexto_historico": "Contexto histórico, social ou geográfico errado",
    "conceito_trocado": "Conceitos confundidos",
    "leitura_parcial": "Leitura parcial do texto",
    "extrapolacao": "Vai além do que o texto permite afirmar",
    "causa_efeito": "Relação de causa e efeito errada",
    "fato_incorreto": "Fato, autor ou dado incorreto",
    "nao_responde": "Verdadeira em si, mas não responde à pergunta",
    "outro": "Outro tipo de erro",
}


class ExplicacaoAlternativaV2(BaseModel):
    letra: Letra
    correta: bool = Field(description="Verdadeiro apenas para a alternativa indicada como correta.")
    tipo_de_erro: TipoDeErro | None = Field(
        description=(
            "Para alternativa incorreta, a natureza do erro: anacronismo (atribui algo a uma época "
            "ou data que não é a sua), contexto_historico (situa o fato em contexto social, político "
            "ou geográfico errado), conceito_trocado (confunde conceitos próximos), leitura_parcial "
            "(usa parte do texto e ignora outra), extrapolacao (afirma mais do que o texto permite), "
            "causa_efeito (inverte ou inventa relação de causa), fato_incorreto (dado, autor ou "
            "evento falso), nao_responde (verdadeira em si, mas não responde à pergunta) ou outro. "
            "Para a alternativa correta: null."
        )
    )
    elemento_incorreto: str | None = Field(
        description=(
            "Para alternativa incorreta: o ponto exato que está errado, como a data, o período, "
            "o autor, o conceito ou a relação afirmada. Para a correta: null."
        )
    )
    por_que: str = Field(
        description=(
            "Para alternativa incorreta: o raciocínio que leva um estudante a escolhê-la e por que "
            "ele não se sustenta. Para a correta: por que ela é a mais adequada."
        )
    )
    como_verificar: str = Field(
        description=(
            "Outros conhecimentos que permitem ao estudante perceber, sem depender do gabarito, se a "
            "alternativa está certa ou errada: as características do período correto, a data ou a "
            "ordem dos acontecimentos, o significado preciso do conceito, ou um fato que a contradiz "
            "ou confirma."
        )
    )
    conceito_envolvido: str = Field(
        description="Conceito central mobilizado pela alternativa, em 2 a 6 palavras."
    )


class CorrecaoObjetivaV2(BaseModel):
    questao_id: str
    alternativa_correta: Letra
    explicacoes: list[ExplicacaoAlternativaV2] = Field(
        description="Uma explicação por alternativa, em ordem alfabética, de A até a última."
    )
    explicacao_correta: str = Field(
        description="O caminho de raciocínio, passo a passo, do enunciado até a resposta correta."
    )
    nivel_dificuldade_estimado: Dificuldade


CONTRATO_POR_PROMPT: dict[str, type[BaseModel]] = {
    "objetiva_v1": CorrecaoObjetiva,
    "objetiva_v2": CorrecaoObjetivaV2,
}


# ---------------------------------------------------------------------------
# Conferência do conteúdo
# ---------------------------------------------------------------------------

def problemas_de_consistencia(
    saida: CorrecaoObjetiva | CorrecaoObjetivaV2, questao_id: int, letras: list[str], gabarito: str
) -> list[str]:
    """Confere a saída com a questão cadastrada. Lista vazia significa saída consistente.

    O formato já foi garantido pela API; aqui se verifica o conteúdo: a resposta
    não pode contrariar o gabarito informado pelo professor nem pular ou repetir
    alternativas. Na versão 2, só as alternativas incorretas têm tipo de erro.
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

    if isinstance(saida, CorrecaoObjetivaV2):
        for e in saida.explicacoes:
            if e.correta and e.tipo_de_erro is not None:
                problemas.append(f"alternativa correta {e.letra} com tipo_de_erro {e.tipo_de_erro}")
            if not e.correta and e.tipo_de_erro is None:
                problemas.append(f"alternativa incorreta {e.letra} sem tipo_de_erro")
    return problemas
