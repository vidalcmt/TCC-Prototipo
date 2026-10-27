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


def test_metrica_liga_custo_a_questao_resposta_e_pessoa(fabrica_sessao, cliente_web):
    from app.models import Correcao, Questao, Submissao, Usuario

    with fabrica_sessao() as s:
        admin = s.query(Usuario).one()
        q1 = Questao(tipo="discursiva", enunciado="E1.")
        q2 = Questao(tipo="objetiva", enunciado="E2.")
        s.add_all([q1, q2])
        s.flush()
        sub = Submissao(questao_id=q1.id, resposta_aluno="R.", codigo_corpus="R021")
        s.add(sub)
        s.flush()
        c = Correcao(submissao_id=sub.id, questao_id=q1.id, feedback_json="{}", modelo="m", prompt_versao="p")
        s.add(c)
        s.flush()
        s.add_all([
            MetricaRequisicao(questao_id=q1.id, submissao_id=sub.id, correcao_id=c.id, usuario_id=admin.id,
                              modelo_solicitado="m", prompt_versao="discursiva_v2", latencia_ms=1,
                              sucesso=True, custo_usd=0.01),
            MetricaRequisicao(questao_id=q1.id, submissao_id=sub.id, modelo_solicitado="m",
                              prompt_versao="discursiva_v2", latencia_ms=1, sucesso=False,
                              motivo_falha="x", custo_usd=0.005),
            MetricaRequisicao(questao_id=q2.id, modelo_solicitado="m", prompt_versao="objetiva_v3",
                              latencia_ms=1, sucesso=True, custo_usd=0.02),
        ])
        s.commit()
        q1_id, sub_id, c_id = q1.id, sub.id, c.id

    pagina = cliente_web.get("/metricas").text
    assert f'href="/respostas/{sub_id}#correcao-{c_id}">R021</a>' in pagina
    assert f'href="/questoes/{q1_id}">Questão {q1_id}</a>' in pagina and ">Ana<" in pagina

    so_q1 = cliente_web.get(f"/metricas?questao={q1_id}").text
    assert f"Chamadas da questão {q1_id}" in so_q1 and "2 chamadas, custo total de US$ 0,015000" in so_q1
    assert "objetiva_v3" not in so_q1.split("Chamadas da questão")[1]

    assert "1 chamada" not in cliente_web.get(f"/metricas?resposta={sub_id}").text
    assert "Chamadas da resposta" in cliente_web.get(f"/metricas?resposta={sub_id}").text

    csv = cliente_web.get("/metricas/exportar.csv").text.splitlines()
    assert csv[0].startswith("id,criado_em,usuario_id,questao_id,submissao_id,correcao_id")
