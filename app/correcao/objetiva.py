"""Geração da explicação de uma questão objetiva (RF02 e RF03)."""

from dataclasses import dataclass

from openai import OpenAI
from sqlalchemy.orm import Session

from app.correcao.contratos import CONTRATO_POR_PROMPT, problemas_de_consistencia
from app.correcao.llm import chamar_modelo
from app.correcao.prompts import carregar_prompt
from app.models import Correcao, MetricaRequisicao, Questao

PROMPT_OBJETIVA = ("objetiva", 2)


@dataclass
class ResultadoExplicacao:
    correcao: Correcao | None
    metrica: MetricaRequisicao

    @property
    def sucesso(self) -> bool:
        return self.correcao is not None


def gabarito_da(questao: Questao) -> str:
    corretas = [a.letra for a in questao.alternativas if a.correta]
    if len(corretas) != 1:
        raise ValueError(f"A questão {questao.id} precisa ter exatamente uma alternativa correta.")
    return corretas[0]


def campos_do_prompt(questao: Questao) -> dict[str, str]:
    return {
        "questao_id": str(questao.id),
        "enunciado": questao.enunciado,
        "alternativas": "\n".join(f"{a.letra}) {a.texto}" for a in questao.alternativas),
        "gabarito": gabarito_da(questao),
    }


def gerar_explicacao(
    sessao: Session, questao: Questao, cliente: OpenAI | None = None
) -> ResultadoExplicacao:
    """Chama o modelo, confere a saída com o gabarito e grava a correção.

    Saída com formato válido mas inconsistente com a questão (gabarito trocado,
    alternativa faltando) não é gravada: a métrica da chamada passa a falha,
    com o motivo, porque uma saída inutilizável conta na taxa de falha.
    """
    prompt = carregar_prompt(*PROMPT_OBJETIVA)
    formato = CONTRATO_POR_PROMPT[prompt.identificador]
    resultado = chamar_modelo(
        sessao, prompt, formato, campos_do_prompt(questao),
        tipo_questao="objetiva", cliente=cliente,
    )
    metrica = resultado.metrica
    if not resultado.sucesso:
        return ResultadoExplicacao(correcao=None, metrica=metrica)

    letras = [a.letra for a in questao.alternativas]
    problemas = problemas_de_consistencia(resultado.saida, questao.id, letras, gabarito_da(questao))
    if problemas:
        metrica.sucesso = False
        metrica.motivo_falha = "saida inconsistente: " + "; ".join(problemas)
        sessao.commit()
        return ResultadoExplicacao(correcao=None, metrica=metrica)

    correcao = Correcao(
        questao_id=questao.id,
        feedback_json=resultado.saida.model_dump_json(),
        modelo=metrica.modelo or metrica.modelo_solicitado,
        prompt_versao=metrica.prompt_versao,
    )
    sessao.add(correcao)
    sessao.flush()
    metrica.correcao_id = correcao.id
    sessao.commit()
    return ResultadoExplicacao(correcao=correcao, metrica=metrica)
