import pytest

from app.metricas.precos import calcular_custo, preco_do_modelo


def test_custo_do_modelo_recomendado():
    # 2.000 tokens de entrada a US$ 2/M + 800 de saída a US$ 10/M = US$ 0,012
    assert calcular_custo("gpt-6.1-sol", 2000, 800) == pytest.approx(0.012)


def test_tokens_de_cache_sao_cobrados_pelo_preco_de_cache():
    # 1.000 normais (US$ 0,002) + 1.000 em cache (US$ 0,0001) + 0 de saída
    assert calcular_custo("gpt-6.1-sol", 2000, 0, tokens_entrada_cache=1000) == pytest.approx(0.0021)


def test_nome_com_sufixo_de_versao_usa_preco_do_nome_base():
    assert preco_do_modelo("gpt-6.1-sol-2026-09-01") == preco_do_modelo("gpt-6.1-sol")


def test_modelo_desconhecido_nao_inventa_custo():
    assert calcular_custo("modelo-inexistente", 100, 100) is None
