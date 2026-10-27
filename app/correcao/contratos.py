"""Contratos de saída do modelo, conforme a seção "Contrato de saída da IA" da especificação.

A API recebe estas classes como formato obrigatório da resposta (saída
estruturada). As descrições dos campos vão junto e orientam o modelo.

Cada versão de prompt tem o seu contrato (CONTRATO_POR_PROMPT). Versões
antigas continuam aqui para que as correções já gravadas possam ser lidas.

Campos com razão metodológica, que não devem ser removidos:
- conceito_envolvido: permite agrupar erros por conceito na análise;
- tipo_de_erro (v2 e v3): permite contar quais tipos de erro os distratores exploram;
- pista (v3): permite contar em quantas alternativas há uma pista de conteúdo
  para eliminá-las;
- trecho_citado (discursiva): distingue feedback específico de genérico, e a
  proporção de critérios com trecho citado é métrica de qualidade;
- usou_resposta_esperada (discursiva): separa as duas condições experimentais.
"""

import re
import unicodedata
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


# ---------------------------------------------------------------------------
# Versão 3 (prompt objetiva_v3): explicação única, pista do enunciado e pista
# para eliminar cada alternativa
# ---------------------------------------------------------------------------

class ExplicacaoAlternativaV3(BaseModel):
    letra: Letra
    correta: bool = Field(description="Verdadeiro apenas para a alternativa indicada como correta.")
    tipo_de_erro: TipoDeErro | None = Field(
        description=(
            "Para alternativa incorreta, a natureza do erro: anacronismo, contexto_historico, "
            "conceito_trocado, leitura_parcial, extrapolacao, causa_efeito, fato_incorreto, "
            "nao_responde ou outro. Para a alternativa correta: null."
        )
    )
    explicacao: str = Field(
        description=(
            "Em até duas frases. Para alternativa incorreta: o que está errado e por quê, numa só "
            "passagem. Para a correta: por que ela é a resposta."
        )
    )
    pista: str | None = Field(
        description=(
            "Só para alternativa incorreta, em uma frase: a pista de conteúdo que permite eliminá-la "
            "sem saber a resposta, como um elemento de outra época, sistema ou conceito incompatível "
            "com o enunciado. Null quando não houver uma pista assim, e sempre null na correta. Nunca "
            "uma pista genérica de prova (tamanho, palavras absolutas, posição da letra)."
        )
    )
    conceito_envolvido: str = Field(
        description="Conceito central mobilizado pela alternativa, em 2 a 6 palavras."
    )


class CorrecaoObjetivaV3(BaseModel):
    questao_id: str
    alternativa_correta: Letra
    pista_do_enunciado: str = Field(
        description=(
            "A palavra, expressão ou dado do enunciado que indica o caminho da resolução e o que ele "
            "sinaliza, em até duas frases."
        )
    )
    explicacoes: list[ExplicacaoAlternativaV3] = Field(
        description="Uma explicação por alternativa, em ordem alfabética, de A até a última."
    )
    explicacao_correta: str = Field(
        description="O caminho do enunciado até a resposta correta, em até quatro passos curtos."
    )
    nivel_dificuldade_estimado: Dificuldade


# ---------------------------------------------------------------------------
# Questão discursiva (prompt discursiva_v1)
# ---------------------------------------------------------------------------

StatusCriterio = Literal["atendido", "parcial", "nao_atendido"]


class AnaliseCriterio(BaseModel):
    criterio: str = Field(
        description="O critério avaliado. Com rubrica, repita o texto do critério do professor."
    )
    peso: float = Field(description="Peso do critério. Com rubrica, o mesmo peso informado pelo professor.")
    status: StatusCriterio
    justificativa: str = Field(
        description=(
            "Por que o critério foi atendido, parcialmente atendido ou não atendido, "
            "referindo-se ao que o aluno escreveu."
        )
    )
    trecho_citado: str | None = Field(
        description=(
            "Trecho copiado literalmente da resposta do aluno que sustenta a avaliação, sem "
            "alterar nenhuma palavra. Null quando o aluno não escreveu nada sobre o critério."
        )
    )


class CorrecaoDiscursiva(BaseModel):
    questao_id: str
    usou_resposta_esperada: bool
    analise_criterios: list[AnaliseCriterio]
    feedback_elaborado: str = Field(
        description=(
            "Texto dirigido ao aluno explicando o que faltou e o caminho para a resposta completa, "
            "com os conhecimentos que ele pode mobilizar para chegar lá."
        )
    )
    nota_sugerida: float
    nota_maxima: float
    confianca: Literal["baixa", "media", "alta"] = Field(
        description="Confiança na nota sugerida; baixa quando a resposta é ambígua ou foge ao tema."
    )


class AnaliseCriterioV2(BaseModel):
    criterio: str = Field(
        description="O critério avaliado. Com rubrica, repita o texto do critério do professor."
    )
    item: str | None = Field(
        description=(
            "Letra do item a que o critério se refere, quando a questão tem itens. Null quando o "
            "critério vale para a resposta inteira ou a questão não tem itens."
        )
    )
    peso: float = Field(description="Peso do critério. Com rubrica, o mesmo peso informado pelo professor.")
    status: StatusCriterio
    justificativa: str = Field(
        description=(
            "Para o professor: por que o critério foi atendido, parcialmente atendido ou não "
            "atendido, referindo-se ao que o aluno escreveu e ao conteúdo esperado."
        )
    )
    trecho_citado: str | None = Field(
        description=(
            "Trecho copiado literalmente da resposta do aluno (do item indicado, quando houver) que "
            "sustenta a avaliação, sem alterar nenhuma palavra. Null quando o aluno não escreveu "
            "nada sobre o critério."
        )
    )


class CorrecaoDiscursivaV2(BaseModel):
    questao_id: str
    usou_resposta_esperada: bool
    analise_criterios: list[AnaliseCriterioV2]
    feedback_elaborado: str = Field(
        description=(
            "Para o aluno: o que ele acertou, o que faltou e onde procurar, sem escrever o conteúdo "
            "que atende ao pedido e sem cobrar o que a rubrica não exige."
        )
    )
    nota_sugerida: float
    nota_maxima: float
    confianca: Literal["baixa", "media", "alta"] = Field(
        description=(
            "Certeza de que a nota está correta, e não a qualidade da resposta. Resposta claramente "
            "errada ou em branco tem confiança alta."
        )
    )
    motivo_confianca: str = Field(description="Uma frase com o motivo do nível de confiança.")


CONTRATO_POR_PROMPT: dict[str, type[BaseModel]] = {
    "objetiva_v1": CorrecaoObjetiva,
    "objetiva_v2": CorrecaoObjetivaV2,
    "objetiva_v3": CorrecaoObjetivaV3,
    "discursiva_v1": CorrecaoDiscursiva,
    "discursiva_v2": CorrecaoDiscursivaV2,
}


# ---------------------------------------------------------------------------
# Conferência do conteúdo
# ---------------------------------------------------------------------------

def problemas_de_consistencia(
    saida: CorrecaoObjetiva | CorrecaoObjetivaV2 | CorrecaoObjetivaV3,
    questao_id: int, letras: list[str], gabarito: str,
) -> list[str]:
    """Confere a saída com a questão cadastrada. Lista vazia significa saída consistente.

    O formato já foi garantido pela API; aqui se verifica o conteúdo: a resposta
    não pode contrariar o gabarito informado pelo professor nem pular ou repetir
    alternativas. Nas versões 2 e 3, só as alternativas incorretas têm tipo de
    erro; na versão 3, a correta também não pode ter pista para eliminá-la.
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

    if isinstance(saida, CorrecaoObjetivaV3):
        for e in saida.explicacoes:
            if e.correta and e.pista is not None:
                problemas.append(f"alternativa correta {e.letra} com pista para eliminá-la")
    if isinstance(saida, (CorrecaoObjetivaV2, CorrecaoObjetivaV3)):
        for e in saida.explicacoes:
            if e.correta and e.tipo_de_erro is not None:
                problemas.append(f"alternativa correta {e.letra} com tipo_de_erro {e.tipo_de_erro}")
            if not e.correta and e.tipo_de_erro is None:
                problemas.append(f"alternativa incorreta {e.letra} sem tipo_de_erro")
    return problemas


def _normalizar(texto: str) -> str:
    """Minúsculas, aspas retas e espaços simples, para comparar trechos citados."""
    texto = unicodedata.normalize("NFC", texto).lower()
    texto = texto.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))
    return re.sub(r"\s+", " ", texto).strip()


def trecho_existe(trecho: str, resposta: str) -> bool:
    """Diz se o trecho citado está de fato na resposta do aluno.

    Aceita diferenças de maiúsculas, aspas e espaços, e trechos com reticências
    no meio, desde que cada parte exista na resposta, na mesma ordem.
    """
    resposta_n = _normalizar(resposta)
    partes = [p.strip(" \"'.,;:") for p in re.split(r"\.\.\.|…|\[\.\.\.\]", _normalizar(trecho))]
    partes = [p for p in partes if p]
    if not partes:
        return False
    posicao = 0
    for parte in partes:
        encontrado = resposta_n.find(parte, posicao)
        if encontrado < 0:
            return False
        posicao = encontrado + len(parte)
    return True


FATOR_STATUS = {"atendido": 1.0, "parcial": 0.5, "nao_atendido": 0.0}


def nota_pelos_criterios(criterios, nota_maxima: float) -> float | None:
    """Nota pela regra do prompt, antes do arredondamento: atendido vale o peso,
    parcial metade e não atendido zero, proporcional à soma dos pesos."""
    soma = sum(c.peso for c in criterios)
    if soma <= 0:
        return None
    return sum(c.peso * FATOR_STATUS[c.status] for c in criterios) / soma * nota_maxima


def problemas_da_discursiva(
    saida: CorrecaoDiscursiva | CorrecaoDiscursivaV2,
    questao_id: int,
    resposta_aluno: str,
    usou_resposta_esperada: bool,
    nota_maxima: float,
    pesos_rubrica: list[float] | None,
    respostas_por_item: dict[str, str] | None = None,
    itens_rubrica: list[str | None] | None = None,
) -> list[str]:
    """Confere a correção discursiva com a questão e a resposta. Lista vazia significa consistente.

    Na versão 2, confere também a letra do item de cada critério, procura o
    trecho citado só na resposta daquele item e refaz a conta da nota.
    """
    problemas = []
    if saida.questao_id != str(questao_id):
        problemas.append(f"questao_id {saida.questao_id!r} diferente de {questao_id}")
    if saida.usou_resposta_esperada != usou_resposta_esperada:
        problemas.append(
            f"usou_resposta_esperada {saida.usou_resposta_esperada} diferente da condição "
            f"executada ({usou_resposta_esperada})"
        )
    if abs(saida.nota_maxima - nota_maxima) > 1e-9:
        problemas.append(f"nota_maxima {saida.nota_maxima} diferente da cadastrada ({nota_maxima})")
    if not 0 <= saida.nota_sugerida <= nota_maxima:
        problemas.append(f"nota_sugerida {saida.nota_sugerida} fora do intervalo 0 a {nota_maxima}")
    if not saida.analise_criterios:
        problemas.append("nenhum critério analisado")

    if pesos_rubrica:
        pesos = [c.peso for c in saida.analise_criterios]
        if len(pesos) != len(pesos_rubrica):
            problemas.append(f"{len(pesos)} critérios analisados, a rubrica tem {len(pesos_rubrica)}")
        elif any(abs(a - b) > 1e-9 for a, b in zip(pesos, pesos_rubrica)):
            problemas.append(f"pesos {pesos} diferentes da rubrica {pesos_rubrica}")

    v2 = isinstance(saida, CorrecaoDiscursivaV2)
    letras = set(respostas_por_item or {})
    if v2:
        for c in saida.analise_criterios:
            if c.item is not None and c.item not in letras:
                problemas.append(
                    f"critério {c.criterio!r} ligado ao item {c.item!r}, que a questão não tem"
                    if letras else f"critério {c.criterio!r} ligado ao item {c.item!r} em questão sem itens"
                )
        if itens_rubrica is not None and pesos_rubrica and len(saida.analise_criterios) == len(itens_rubrica):
            recebidos = [c.item for c in saida.analise_criterios]
            if recebidos != itens_rubrica:
                problemas.append(f"itens dos critérios {recebidos} diferentes da rubrica {itens_rubrica}")

        bruta = nota_pelos_criterios(saida.analise_criterios, nota_maxima)
        multiplo = abs(saida.nota_sugerida * 2 - round(saida.nota_sugerida * 2)) < 1e-9
        if bruta is not None and (not multiplo or abs(saida.nota_sugerida - bruta) > 0.25 + 1e-9):
            problemas.append(
                f"nota_sugerida {saida.nota_sugerida} não corresponde aos critérios "
                f"(a conta dá {bruta:.2f}, arredondada para múltiplo de 0,5)"
            )

    for c in saida.analise_criterios:
        if not c.trecho_citado:
            continue
        item = getattr(c, "item", None)
        if item in letras:
            if not trecho_existe(c.trecho_citado, respostas_por_item[item]):
                problemas.append(f"trecho citado no critério {c.criterio!r} não existe na resposta do item {item}")
        elif not trecho_existe(c.trecho_citado, resposta_aluno):
            problemas.append(f"trecho citado no critério {c.criterio!r} não existe na resposta do aluno")
    return problemas
