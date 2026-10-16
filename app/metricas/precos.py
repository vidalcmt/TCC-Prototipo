"""Cálculo de custo a partir dos tokens lidos da resposta da API.

Os tokens nunca são estimados: vêm do campo usage de cada resposta. Os preços
vêm de config/precos.toml, que registra também a fonte e a data de acesso.
"""

import tomllib
from dataclasses import dataclass
from functools import lru_cache

from app.config import RAIZ

ARQUIVO_PRECOS = RAIZ / "config" / "precos.toml"
UM_MILHAO = 1_000_000


@dataclass(frozen=True)
class Preco:
    entrada: float
    entrada_cache: float
    escrita_cache: float
    saida: float


@lru_cache
def carregar_tabela() -> dict:
    with open(ARQUIVO_PRECOS, "rb") as arquivo:
        return tomllib.load(arquivo)


def preco_do_modelo(modelo: str) -> Preco | None:
    """Procura o preço pelo nome exato e, se não achar, pelo nome base.

    A API pode devolver um identificador com sufixo de versão (por exemplo,
    "gpt-6.1-sol-2026-09-01"); nesse caso vale o preço do nome base.
    """
    modelos = carregar_tabela()["modelos"]
    if modelo in modelos:
        return Preco(**modelos[modelo])
    for nome in sorted(modelos, key=len, reverse=True):
        if modelo.startswith(nome):
            return Preco(**modelos[nome])
    return None


def calcular_custo(
    modelo: str,
    tokens_entrada: int,
    tokens_saida: int,
    tokens_entrada_cache: int = 0,
    tokens_escrita_cache: int = 0,
) -> float | None:
    """Custo em dólares de uma requisição.

    Considera que tokens_entrada é o total de entrada, que já inclui os tokens
    lidos do cache e os gravados nele; por isso eles são descontados da parcela
    cobrada pelo preço cheio.
    """
    preco = preco_do_modelo(modelo)
    if preco is None:
        return None
    entrada_normal = max(tokens_entrada - tokens_entrada_cache - tokens_escrita_cache, 0)
    custo = (
        entrada_normal * preco.entrada
        + tokens_entrada_cache * preco.entrada_cache
        + tokens_escrita_cache * preco.escrita_cache
        + tokens_saida * preco.saida
    )
    return custo / UM_MILHAO
