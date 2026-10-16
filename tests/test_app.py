from fastapi.testclient import TestClient

from app.database import obter_sessao
from app.main import app
from app.models import MetricaRequisicao


def cliente_com_banco(fabrica_sessao):
    def sessao_de_teste():
        with fabrica_sessao() as s:
            yield s

    app.dependency_overrides[obter_sessao] = sessao_de_teste
    return TestClient(app)


def test_saude():
    resposta = TestClient(app).get("/saude")
    assert resposta.status_code == 200 and resposta.json()["status"] == "ok"


def test_pagina_e_exportacao_de_metricas(fabrica_sessao):
    with fabrica_sessao() as s:
        s.add(MetricaRequisicao(
            modelo_solicitado="gpt-6.1-sol", prompt_versao="teste_v1",
            latencia_ms=850.0, sucesso=False, motivo_falha="teste",
        ))
        s.commit()

    cliente = cliente_com_banco(fabrica_sessao)
    try:
        pagina = cliente.get("/metricas")
        assert pagina.status_code == 200 and "teste_v1" in pagina.text

        csv = cliente.get("/metricas/exportar.csv")
        linhas = csv.text.strip().splitlines()
        assert linhas[0].startswith("id,criado_em")
        assert len(linhas) == 2 and "teste_v1" in linhas[1]
    finally:
        app.dependency_overrides.clear()
