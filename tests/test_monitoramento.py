"""Monitoramento: medida de cada requisição e página de acompanhamento."""

import logging
from datetime import timedelta

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.models import Alternativa, Folha, LeituraPagina, MetricaRequisicao, PaginaDigitalizada, RequisicaoHttp, agora
from app.monitoramento import medidor
from app.monitoramento.resumo import montar, percentil
from tests.conftest import criar_usuario, entrar


def _requisicoes(fabrica_sessao):
    with fabrica_sessao() as s:
        return [(r.metodo, r.rota, r.status) for r in s.query(RequisicaoHttp).order_by(RequisicaoHttp.id)]


def test_grava_a_rota_declarada_e_nunca_o_endereco_real(fabrica_sessao, cliente_web):
    antes = len(_requisicoes(fabrica_sessao))
    cliente_web.get("/r/ABCD-EFGH")
    cliente_web.get("/questoes/999999")
    cliente_web.get("/static/estilo.css")
    cliente_web.get("/saude")
    cliente_web.get("/nao-existe")
    novas = _requisicoes(fabrica_sessao)[antes:]
    assert ("GET", "/r/{codigo}", 404) in novas
    assert ("GET", "/questoes/{questao_id}", 404) in novas
    assert ("GET", "(sem rota)", 404) in novas
    assert not any("ABCD" in rota or "999999" in rota for _, rota, _ in novas)
    assert not any(rota.startswith(("/static", "/saude")) for _, rota, _ in novas)


def _app_de_teste():
    def lenta(request):
        return PlainTextResponse("ok")

    def quebra(request):
        raise RuntimeError("falha de teste")

    return Starlette(routes=[Route("/ok", lenta), Route("/erro/{id}", quebra)])


def test_erro_do_servidor_e_requisicao_lenta_vao_para_o_log(fabrica_sessao, monkeypatch, caplog):
    monkeypatch.setattr(medidor, "obter_fabrica_sessao", lambda: fabrica_sessao)
    monkeypatch.setattr(medidor, "LENTA_MS", 0.0)  # toda requisição conta como lenta
    cliente = TestClient(medidor.MedidorDeRequisicoes(_app_de_teste()), raise_server_exceptions=False)
    with caplog.at_level(logging.WARNING, logger="devolutiva.monitoramento"):
        assert cliente.get("/ok").status_code == 200
        assert cliente.get("/erro/7").status_code == 500
    with fabrica_sessao() as s:
        linhas = [(r.rota, r.status) for r in s.query(RequisicaoHttp).order_by(RequisicaoHttp.id)]
    assert linhas == [("/ok", 200), ("/erro/{id}", 500)]
    mensagens = [r.getMessage() for r in caplog.records]
    assert any("lenta" in m and "rota=/ok" in m for m in mensagens)
    assert any("com_erro" in m and "rota=/erro/{id}" in m and "status=500" in m for m in mensagens)


def test_registros_antigos_sao_apagados(fabrica_sessao, monkeypatch):
    monkeypatch.setattr(medidor, "obter_fabrica_sessao", lambda: fabrica_sessao)
    with fabrica_sessao() as s:
        s.add(RequisicaoHttp(criado_em=agora() - timedelta(days=40), metodo="GET", rota="/velha", status=200,
                             duracao_ms=1))
        s.commit()
    TestClient(medidor.MedidorDeRequisicoes(_app_de_teste())).get("/ok")
    with fabrica_sessao() as s:
        assert [r.rota for r in s.query(RequisicaoHttp)] == ["/ok"]


@pytest.mark.parametrize("valores, p, esperado", [
    ([], 50, None), ([10], 95, 10), ([1, 2, 3, 4], 50, 2.5), (list(range(1, 101)), 95, 95.05),
])
def test_percentil(valores, p, esperado):
    assert percentil(valores, p) == (pytest.approx(esperado) if esperado is not None else None)


def test_resumo_do_periodo(fabrica_sessao):
    with fabrica_sessao() as s:
        for d in (100, 200, 300, 4000):
            s.add(RequisicaoHttp(metodo="GET", rota="/atividades/{atividade_id}", status=200, duracao_ms=d))
        s.add(RequisicaoHttp(metodo="POST", rota="/atividades/{atividade_id}/digitalizacoes", status=502,
                             duracao_ms=50))
        s.add(RequisicaoHttp(criado_em=agora() - timedelta(days=2), metodo="GET", rota="/antiga", status=200,
                             duracao_ms=9999))
        s.add_all([
            MetricaRequisicao(tipo_questao="discursiva", modelo_solicitado="m", prompt_versao="discursiva_v2",
                              latencia_ms=12000, sucesso=True),
            MetricaRequisicao(tipo_questao="discursiva", modelo_solicitado="m", prompt_versao="discursiva_v2",
                              latencia_ms=500, sucesso=False, motivo_falha="x"),
        ])
        s.commit()
        painel = montar(s, "24h")
    assert painel.geral.total == 5 and painel.geral.erros == 1 and painel.lentas == 1
    assert painel.por_rota[0][0] == "GET /atividades/{atividade_id}" and painel.por_rota[0][1].maximo == 4000
    assert painel.mais_lentas[0].duracao_ms == 4000 and painel.erros_recentes[0].status == 502
    assert sum(i.total for i in painel.intervalos) == 5 and 24 <= len(painel.intervalos) <= 26
    (nome, modelo), = painel.modelo
    assert nome == "Discursivas" and modelo.total == 2 and modelo.erros == 1 and modelo.p50 == 12000
    assert "memoria_processo" in painel.servidor and painel.servidor["disco_total"] > 0
    assert montar(s, "7d").geral.total == 6 and montar(s, "inexistente").periodo == "24h"


def test_pagina_so_para_administradores(fabrica_sessao, cliente_web, cliente_anonimo):
    cliente_web.get("/atividades")
    pagina = cliente_web.get("/monitoramento?periodo=1h").text
    assert "Monitoramento" in pagina and "GET /atividades" in pagina and "<svg" in pagina
    assert 'href="/monitoramento"' in cliente_web.get("/").text
    csv = cliente_web.get("/monitoramento/requisicoes.csv")
    assert csv.headers["content-type"].startswith("text/csv") and "/atividades" in csv.text

    criar_usuario(fabrica_sessao, email="prof@teste.com", nome="Bruno Prof", papel="avaliador")
    cliente_web.post("/sair")
    entrar(cliente_anonimo, "prof@teste.com")
    assert cliente_anonimo.get("/monitoramento").status_code == 403
    assert 'href="/monitoramento"' not in cliente_anonimo.get("/").text
