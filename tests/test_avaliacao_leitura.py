"""Avaliação da leitura pelo administrador e leitura de todas as páginas de novo."""

import pytest

from app.config import config
from app.leitura import lote as lote_leitura
from app.leitura import ocr
from app.leitura.avaliacao import resumo
from app.main import app
from app.models import AvaliacaoLeitura, LeituraPagina
from app.questoes.cliente import obter_cliente_llm
from tests.conftest import criar_usuario, entrar
from tests.falsos import ClienteFalso, resposta_falsa
from tests.test_leitura import _enviar_folha
from tests.test_resultados import _LinhaSincrona, _url, prova  # noqa: F401
from tests.test_revisor import _saida


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "pasta_arquivos", tmp_path)
    monkeypatch.setattr(lote_leitura.threading, "Thread", _LinhaSincrona)
    lote_leitura._andamentos.clear()


def _ler_com_revisao(fabrica_sessao, cliente_web, p, monkeypatch, texto="Houve êxodo rural."):
    monkeypatch.setattr(config, "leitura_revisao_ia", True)
    original = ocr.transcrever

    def transcrever(*args, **kw):
        textos, latencia, servico = original(*args, **kw)
        return {c: t.replace("êxodo", "exodo") for c, t in textos.items()}, latencia, servico
    cliente = ClienteFalso(resposta_falsa(_saida(texto, [("exodo", "êxodo", "o acento está na imagem")])))
    app.dependency_overrides[obter_cliente_llm] = lambda: cliente
    _enviar_folha(fabrica_sessao, cliente_web, p, {p["o1"]: "B"}, monkeypatch=monkeypatch)
    monkeypatch.setattr(ocr, "transcrever", transcrever)
    cliente_web.post(f"{_url(p)}/ler")
    return cliente


def _avaliar(cliente_web, p, nota, erro=False):
    dados = {"campo": f"q{p['d']}", "nota": nota}
    if erro:
        dados["corrigiu_erro_aluno"] = "1"
    return cliente_web.post(f"{_url(p)}/avaliacao-leitura", data=dados)


def test_avaliar_a_leitura_de_uma_resposta(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    _ler_com_revisao(fabrica_sessao, cliente_web, p, monkeypatch)
    pagina = cliente_web.get(_url(p)).text
    assert "Avaliação da leitura" in pagina and "leitura com a revisão da IA" in pagina
    assert f'name="aval-q{p["d"]}" value="correta"' in pagina and "A IA corrigiu um erro do aluno" in pagina

    r = _avaliar(cliente_web, p, "pequenos_erros")
    assert r.json() == {"ok": True, "nota": "pequenos_erros", "rotulo": "Pequenos erros", "corrigiu_erro_aluno": False}
    r = _avaliar(cliente_web, p, "correta", erro=True)  # mudar de ideia atualiza a mesma avaliação
    assert r.json()["nota"] == "correta"
    with fabrica_sessao() as s:
        a = s.query(AvaliacaoLeitura).one()
        assert (a.nota, a.corrigiu_erro_aluno, a.com_revisao, a.trocas) == ("correta", True, True, 1)
        assert a.texto_lido == "Houve êxodo rural." and a.texto_ocr == "Houve exodo rural."
        assert a.servico_ocr == "google-cloud-vision"
    assert f'name="aval-q{p["d"]}" value="correta" checked' in cliente_web.get(_url(p)).text

    assert _avaliar(cliente_web, p, "otima").status_code == 400
    assert cliente_web.post(f"{_url(p)}/avaliacao-leitura", data={"campo": "q999", "nota": "correta"}).status_code == 400


def test_avaliacao_mostra_o_texto_lido_mesmo_com_resposta_salva(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    _ler_com_revisao(fabrica_sessao, cliente_web, p, monkeypatch)
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", f"q{p['o2']}": "branco",
                                                     f"q{p['d']}": "Houve êxodo rural!"})
    pagina = cliente_web.get(_url(p)).text
    assert ">Houve êxodo rural!</textarea>" in pagina  # a resposta salva no formulário
    assert '<span class="discreto">Texto lido:</span> Houve êxodo rural.' in pagina  # e o que foi lido, para avaliar
    assert "<p>Houve <del>exodo</del> rural.</p>" in pagina


def test_so_administrador_avalia(fabrica_sessao, cliente_web, cliente_anonimo, prova, monkeypatch):
    p = prova
    _ler_com_revisao(fabrica_sessao, cliente_web, p, monkeypatch)
    criar_usuario(fabrica_sessao, email="prof@teste.com", nome="Paula", papel="avaliador")
    cliente_web.cookies.clear()
    entrar(cliente_web, "prof@teste.com")
    assert "Avaliação da leitura" not in cliente_web.get(_url(p)).text
    assert _avaliar(cliente_web, p, "correta").status_code in (302, 303, 403)
    assert cliente_web.get("/leitura/avaliacoes").status_code in (302, 303, 403)
    with fabrica_sessao() as s:
        assert s.query(AvaliacaoLeitura).count() == 0


def test_ler_tudo_de_novo_mantem_a_conferencia_e_separa_as_avaliacoes(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    _ler_com_revisao(fabrica_sessao, cliente_web, p, monkeypatch)
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", f"q{p['o2']}": "branco",
                                                     f"q{p['d']}": "Houve êxodo rural."})
    _avaliar(cliente_web, p, "muitos_erros")

    pagina = cliente_web.get(f"/atividades/{p['atividade']}/digitalizacoes").text
    assert "Ler de novo todas as páginas" in pagina
    cliente_web.post(f"/atividades/{p['atividade']}/digitalizacoes/ler-de-novo", data={"confirmo": "on"})
    with fabrica_sessao() as s:
        leitura = s.query(LeituraPagina).one()
        assert leitura.conferida_em is not None  # as respostas salvas continuam sendo a referência
        a = s.query(AvaliacaoLeitura).one()
        assert a.leitura_pagina_id is None and a.nota == "muitos_erros"  # a avaliação antiga fica guardada

    # a nova leitura recebe a sua própria avaliação; o resumo conta uma por folha, campo e condição
    assert 'value="muitos_erros" checked' not in cliente_web.get(_url(p)).text
    _avaliar(cliente_web, p, "correta")
    with fabrica_sessao() as s:
        assert s.query(AvaliacaoLeitura).count() == 2
        total, grupos = resumo(s)
    assert total.total == 1 and total.notas["correta"] == 1
    assert [g.nome for g in grupos] == ["Cloud Vision com revisão da IA"]

    pagina = cliente_web.get("/leitura/avaliacoes").text
    assert "Cloud Vision com revisão da IA" in pagina and "100,0%" in pagina
    csv = cliente_web.get("/leitura/avaliacoes.csv").text
    assert csv.splitlines()[0].startswith("atividade,folha,campo,nota") and len(csv.splitlines()) == 3


def test_resumo_separa_leitura_com_e_sem_revisao(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    monkeypatch.setattr(config, "leitura_revisao_ia", False)
    _enviar_folha(fabrica_sessao, cliente_web, p, {}, monkeypatch=monkeypatch)
    cliente_web.post(f"{_url(p)}/ler")
    pagina = cliente_web.get(_url(p)).text
    assert "Avaliação da leitura" in pagina and "leitura com a revisão da IA" not in pagina
    _avaliar(cliente_web, p, "pequenos_erros")
    _ler_com_revisao(fabrica_sessao, cliente_web, p, monkeypatch)
    _avaliar(cliente_web, p, "correta")
    with fabrica_sessao() as s:
        total, grupos = resumo(s)
    assert {g.nome: dict(g.notas) for g in grupos} == {"Cloud Vision com revisão da IA": {"correta": 1},
                                                       "Cloud Vision sem revisão": {"pequenos_erros": 1}}


def test_pagina_sem_avaliacoes(cliente_web):
    assert "Nenhuma leitura avaliada ainda" in cliente_web.get("/leitura/avaliacoes").text
