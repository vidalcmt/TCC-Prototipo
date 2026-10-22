"""Correção de uma resposta discursiva (RF06, RF07 e RF08)."""

from dataclasses import dataclass

from openai import OpenAI
from sqlalchemy.orm import Session

from app.correcao.contratos import CONTRATO_POR_PROMPT, problemas_da_discursiva
from app.correcao.llm import chamar_modelo
from app.correcao.prompts import carregar_prompt
from app.models import Correcao, MetricaRequisicao, Questao, Submissao

PROMPT_DISCURSIVA = ("discursiva", 1)

SEM_RUBRICA = "O professor não informou rubrica. Defina os critérios conforme a regra 2."
SEM_RESPOSTA_ESPERADA = (
    "O professor não informou resposta esperada. Avalie com base no enunciado e no "
    "conhecimento esperado no ensino médio."
)


class CondicaoIndisponivel(ValueError):
    """Pedido de correção com resposta esperada para questão que não tem uma."""


@dataclass
class ResultadoCorrecao:
    correcao: Correcao | None
    metrica: MetricaRequisicao

    @property
    def sucesso(self) -> bool:
        return self.correcao is not None


def formatar_numero(valor: float) -> str:
    return f"{valor:g}".replace(".", ",")


def campos_do_prompt(questao: Questao, submissao: Submissao, usar_resposta_esperada: bool) -> dict[str, str]:
    if questao.criterios:
        rubrica = "\n".join(
            f"{i}. {c.descricao} (peso {formatar_numero(c.peso)})"
            for i, c in enumerate(questao.criterios, start=1)
        )
    else:
        rubrica = SEM_RUBRICA

    if usar_resposta_esperada:
        resposta_esperada = questao.resposta_esperada.texto
        condicao = "com resposta esperada; use-a como referência, sem exigir as mesmas palavras."
    else:
        resposta_esperada = SEM_RESPOSTA_ESPERADA
        condicao = "sem resposta esperada."

    return {
        "questao_id": str(questao.id),
        "nota_maxima": formatar_numero(questao.nota_maxima),
        "enunciado": questao.enunciado,
        "rubrica": rubrica,
        "resposta_esperada": resposta_esperada,
        "resposta_aluno": submissao.resposta_aluno or "",
        "condicao": condicao,
        "usou_resposta_esperada": "true" if usar_resposta_esperada else "false",
    }


def gerar_correcao(
    sessao: Session,
    submissao: Submissao,
    usar_resposta_esperada: bool,
    cliente: OpenAI | None = None,
) -> ResultadoCorrecao:
    """Corrige a resposta em uma das duas condições experimentais (RF08).

    A condição pedida é gravada na métrica e na correção. Saída inconsistente
    (condição trocada, nota fora do intervalo, trecho citado que não existe na
    resposta, critérios diferentes da rubrica) não é gravada e conta como falha.
    """
    questao = sessao.get(Questao, submissao.questao_id)
    if usar_resposta_esperada and questao.resposta_esperada is None:
        raise CondicaoIndisponivel("Esta questão não tem resposta esperada cadastrada.")

    prompt = carregar_prompt(*PROMPT_DISCURSIVA)
    resultado = chamar_modelo(
        sessao, prompt, CONTRATO_POR_PROMPT[prompt.identificador],
        campos_do_prompt(questao, submissao, usar_resposta_esperada),
        tipo_questao="discursiva", usou_resposta_esperada=usar_resposta_esperada, cliente=cliente,
    )
    metrica = resultado.metrica
    if not resultado.sucesso:
        return ResultadoCorrecao(correcao=None, metrica=metrica)

    problemas = problemas_da_discursiva(
        resultado.saida,
        questao_id=questao.id,
        resposta_aluno=submissao.resposta_aluno or "",
        usou_resposta_esperada=usar_resposta_esperada,
        nota_maxima=questao.nota_maxima,
        pesos_rubrica=[c.peso for c in questao.criterios] or None,
    )
    if problemas:
        metrica.sucesso = False
        metrica.motivo_falha = "saida inconsistente: " + "; ".join(problemas)
        sessao.commit()
        return ResultadoCorrecao(correcao=None, metrica=metrica)

    correcao = Correcao(
        submissao_id=submissao.id,
        questao_id=questao.id,
        feedback_json=resultado.saida.model_dump_json(),
        nota_sugerida=resultado.saida.nota_sugerida,
        usou_resposta_esperada=usar_resposta_esperada,
        modelo=metrica.modelo or metrica.modelo_solicitado,
        prompt_versao=metrica.prompt_versao,
    )
    sessao.add(correcao)
    sessao.flush()
    metrica.correcao_id = correcao.id
    sessao.commit()
    return ResultadoCorrecao(correcao=correcao, metrica=metrica)
