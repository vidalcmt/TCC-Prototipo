from fastapi.testclient import TestClient

from app.main import app
from app.models import MetricaRequisicao


def test_saude_e_publica():
    resposta = TestClient(app).get("/saude")
    assert resposta.status_code == 200 and resposta.json()["status"] == "ok"


def test_pagina_e_exportacao_de_metricas(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        s.add(MetricaRequisicao(
            modelo_solicitado="gpt-6.1-sol", prompt_versao="teste_v1",
            latencia_ms=850.0, sucesso=False, motivo_falha="teste",
        ))
        s.commit()

    pagina = cliente_web.get("/metricas")
    assert pagina.status_code == 200 and "teste_v1" in pagina.text

    csv = cliente_web.get("/metricas/exportar.csv")
    linhas = csv.text.strip().splitlines()
    assert linhas[0].startswith("id,criado_em,usuario_id")
    assert len(linhas) == 2 and "teste_v1" in linhas[1]
