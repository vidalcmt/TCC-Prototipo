"""A instrumentação precisa registrar toda chamada, com sucesso ou falha.

Os testes usam um cliente falso no lugar da API, então não gastam crédito.
"""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.correcao.llm import chamar_modelo
from app.correcao.prompts import carregar_prompt
from app.models import MetricaRequisicao


class Eco(BaseModel):
    eco: str


def resposta_falsa(saida, status="completed"):
    uso = SimpleNamespace(
        input_tokens=1200,
        input_tokens_details=SimpleNamespace(cached_tokens=200, cache_write_tokens=0),
        output_tokens=300,
        output_tokens_details=SimpleNamespace(reasoning_tokens=100),
    )
    return SimpleNamespace(
        model="gpt-6.1-sol-2026-09-01",
        usage=uso,
        output_parsed=saida,
        status=status,
        incomplete_details=None if status == "completed" else {"reason": "max_output_tokens"},
    )


class ClienteFalso:
    def __init__(self, resposta=None, erro=None):
        self.responses = SimpleNamespace(parse=self._parse)
        self._resposta, self._erro = resposta, erro
        self.chamadas = []

    def _parse(self, **kwargs):
        self.chamadas.append(kwargs)
        if self._erro:
            raise self._erro
        return self._resposta


@pytest.fixture
def prompt():
    return carregar_prompt("teste", 1)


def test_sucesso_grava_tokens_custo_latencia_modelo_e_prompt(sessao, prompt):
    cliente = ClienteFalso(resposta_falsa(Eco(eco="ok")))
    resultado = chamar_modelo(
        sessao, prompt, Eco, {"frase": "ok"}, tipo_questao="discursiva",
        usou_resposta_esperada=True, cliente=cliente,
    )

    assert resultado.sucesso and resultado.saida.eco == "ok"
    m = sessao.get(MetricaRequisicao, resultado.metrica.id)
    assert m.modelo == "gpt-6.1-sol-2026-09-01"
    assert m.modelo_solicitado == "gpt-6.1-sol"
    assert m.prompt_versao == "teste_v1"
    assert (m.tokens_entrada, m.tokens_entrada_cache, m.tokens_saida) == (1200, 200, 300)
    assert m.tokens_raciocinio == 100
    # 1.000 normais a 2 + 200 em cache a 0,10 + 300 de saída a 10, por milhão
    assert m.custo_usd == pytest.approx((1000 * 2 + 200 * 0.10 + 300 * 10) / 1e6)
    assert m.latencia_ms >= 0
    assert m.tipo_questao == "discursiva" and m.usou_resposta_esperada is True
    # O prompt chegou preenchido à API
    assert "ok" in cliente.chamadas[0]["input"][1]["content"]
    assert cliente.chamadas[0]["text_format"] is Eco


def test_resposta_sem_saida_estruturada_e_registrada_como_falha(sessao, prompt):
    cliente = ClienteFalso(resposta_falsa(None, status="incomplete"))
    resultado = chamar_modelo(sessao, prompt, Eco, {"frase": "x"}, cliente=cliente)

    assert not resultado.sucesso and resultado.saida is None
    m = resultado.metrica
    assert "sem saida estruturada" in m.motivo_falha
    # Mesmo na falha, os tokens consumidos são registrados (eles são cobrados)
    assert m.tokens_entrada == 1200 and m.custo_usd is not None


def test_erro_de_rede_e_registrado_com_motivo(sessao, prompt):
    cliente = ClienteFalso(erro=ConnectionError("sem internet"))
    resultado = chamar_modelo(sessao, prompt, Eco, {"frase": "x"}, cliente=cliente)

    assert not resultado.sucesso
    assert sessao.query(MetricaRequisicao).count() == 1
    assert resultado.metrica.motivo_falha == "ConnectionError: sem internet"
    assert resultado.metrica.tokens_entrada is None
