"""Ponto único de chamada ao modelo de linguagem.

Toda requisição passa por chamar_modelo(), que:
1. mede a latência do envio até a resposta completa;
2. pede saída estruturada, validada contra um modelo Pydantic;
3. lê os tokens da resposta da API (nunca estimados) e calcula o custo;
4. grava uma linha em metrica_requisicao, com sucesso ou falha e o motivo.

Assim, nenhuma chamada fica sem medição, inclusive as que falham.
"""

import time
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import config
from app.correcao.prompts import Prompt
from app.metricas.precos import calcular_custo
from app.models import MetricaRequisicao

Formato = TypeVar("Formato", bound=BaseModel)

_cliente: OpenAI | None = None


def cliente_padrao() -> OpenAI:
    global _cliente
    if _cliente is None:
        if not config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY não definida. Copie .env.example para .env.")
        _cliente = OpenAI(api_key=config.openai_api_key)
    return _cliente


@dataclass
class ResultadoChamada(Generic[Formato]):
    saida: Formato | None
    metrica: MetricaRequisicao

    @property
    def sucesso(self) -> bool:
        return self.metrica.sucesso


def _campo(objeto: Any, *nomes: str) -> int:
    """Lê um campo aninhado de usage, devolvendo 0 quando ele não existe."""
    for nome in nomes:
        objeto = getattr(objeto, nome, None)
        if objeto is None:
            return 0
    return int(objeto)


def chamar_modelo(
    sessao: Session,
    prompt: Prompt,
    formato: type[Formato],
    campos: dict[str, str],
    *,
    tipo_questao: str | None = None,
    usou_resposta_esperada: bool | None = None,
    modelo: str | None = None,
    cliente: OpenAI | None = None,
) -> ResultadoChamada[Formato]:
    modelo = modelo or config.modelo
    metrica = MetricaRequisicao(
        tipo_questao=tipo_questao,
        usou_resposta_esperada=usou_resposta_esperada,
        modelo_solicitado=modelo,
        prompt_versao=prompt.identificador,
        sucesso=False,
        latencia_ms=0.0,
    )
    saida: Formato | None = None

    inicio = time.perf_counter()
    try:
        resposta = (cliente or cliente_padrao()).responses.parse(
            model=modelo,
            input=prompt.mensagens(**campos),
            text_format=formato,
        )
        metrica.latencia_ms = (time.perf_counter() - inicio) * 1000

        uso = resposta.usage
        metrica.modelo = resposta.model
        metrica.tokens_entrada = _campo(uso, "input_tokens")
        metrica.tokens_entrada_cache = _campo(uso, "input_tokens_details", "cached_tokens")
        metrica.tokens_escrita_cache = _campo(uso, "input_tokens_details", "cache_write_tokens")
        metrica.tokens_saida = _campo(uso, "output_tokens")
        metrica.tokens_raciocinio = _campo(uso, "output_tokens_details", "reasoning_tokens")
        metrica.custo_usd = calcular_custo(
            resposta.model or modelo,
            metrica.tokens_entrada,
            metrica.tokens_saida,
            metrica.tokens_entrada_cache,
            metrica.tokens_escrita_cache,
        )

        saida = resposta.output_parsed
        if saida is None:
            # Recusa do modelo ou resposta cortada pelo limite de tokens.
            detalhe = getattr(resposta, "incomplete_details", None)
            metrica.motivo_falha = (
                f"sem saida estruturada (status={resposta.status}, detalhe={detalhe})"
            )
        else:
            metrica.sucesso = True
    except Exception as erro:  # rede, autenticação, validação do esquema etc.
        if not metrica.latencia_ms:
            metrica.latencia_ms = (time.perf_counter() - inicio) * 1000
        metrica.motivo_falha = f"{type(erro).__name__}: {erro}"[:2000]
        saida = None

    sessao.add(metrica)
    sessao.commit()
    return ResultadoChamada(saida=saida, metrica=metrica)
