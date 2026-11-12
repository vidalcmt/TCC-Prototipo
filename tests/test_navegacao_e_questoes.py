"""Seletor de folhas com a situação de cada uma, e questões criadas de dentro da atividade."""

import pytest

from app.config import config
from app.leitura import lote as lote_leitura
from app.models import Atividade, Questao
from tests.test_leitura import _enviar_folha
from tests.test_resultados import _LinhaSincrona, _url, prova  # noqa: F401


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "pasta_arquivos", tmp_path)
    monkeypatch.setattr(lote_leitura.threading, "Thread", _LinhaSincrona)
    lote_leitura._andamentos.clear()


def test_seletor_mostra_todas_as_folhas_com_leitura_e_correcao(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    monkeypatch.setattr(config, "leitura_revisao_ia", False)
    _enviar_folha(fabrica_sessao, cliente_web, p, {p["o1"]: "B"}, monkeypatch=monkeypatch)
    cliente_web.post(f"{_url(p)}/ler")
    pagina = cliente_web.get(_url(p, 2)).text  # da terceira folha dá para ir direto para a primeira
    assert "Folha 3 de 3" in pagina
    for i, codigo in enumerate(p["codigos"]):
        assert f'href="/atividades/{p["atividade"]}/folhas/{p["folhas"][i]}"' in pagina and codigo in pagina
    assert f'href="/atividades/{p["atividade"]}/folhas/{p["folhas"][2]}" aria-current="page"' in pagina
    assert pagina.count("Sem digitalização") == 2 and "Lida, a conferir" in pagina
    assert pagina.count("Sem respostas") >= 3

    # o professor salva a primeira: lida e conferida, e a correção passa a ter situação
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", f"q{p['o2']}": "branco",
                                                     f"q{p['d']}": "Houve êxodo rural."})
    pagina = cliente_web.get(_url(p, 1)).text
    assert "Lida e conferida" in pagina and "1 a corrigir" in pagina


def test_criar_objetiva_dentro_da_atividade(cliente_web, fabrica_sessao):
    with fabrica_sessao() as s:
        a = Atividade(titulo="Revisão de História")
        s.add(a)
        s.commit()
        atividade_id = a.id
    pagina = cliente_web.get(f"/atividades/{atividade_id}").text
    assert f'href="/questoes/nova?atividade={atividade_id}"' in pagina
    assert f'href="/questoes/nova-discursiva?atividade={atividade_id}"' in pagina

    formulario = cliente_web.get(f"/questoes/nova?atividade={atividade_id}").text
    assert "será incluída no fim da atividade <strong>Revisão de História</strong>" in formulario
    assert f'name="atividade_id" value="{atividade_id}"' in formulario

    dados = {"enunciado": "Quem proclamou a República?", "correta": "A", "atividade_id": str(atividade_id),
             **{f"alternativa_{l}": f"Opção {l}" for l in "ABCDE"}}
    r = cliente_web.post("/questoes", data=dados, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith(f"/atividades/{atividade_id}?aviso=")
    assert "inclu%C3%ADda%20na%20atividade%20como%20quest%C3%A3o%201" in r.headers["location"]
    with fabrica_sessao() as s:
        assert [i.questao.enunciado for i in s.get(Atividade, atividade_id).itens] == ["Quem proclamou a República?"]

    # com erro, o formulário volta com a atividade de destino
    r = cliente_web.post("/questoes", data={"atividade_id": str(atividade_id)})
    assert r.status_code == 400 and "Revisão de História" in r.text


def test_criar_discursiva_dentro_da_atividade(cliente_web, fabrica_sessao):
    with fabrica_sessao() as s:
        a = Atividade(titulo="Biologia")
        s.add(a)
        s.commit()
        atividade_id = a.id
    assert "Biologia" in cliente_web.get(f"/questoes/nova-discursiva?atividade={atividade_id}").text
    r = cliente_web.post("/questoes/discursivas", data={"enunciado": "Explique a mitose.", "nota_maxima": "10",
                                                        "atividade_id": str(atividade_id)}, follow_redirects=False)
    assert r.headers["location"].startswith(f"/atividades/{atividade_id}?aviso=")
    with fabrica_sessao() as s:
        itens = s.get(Atividade, atividade_id).itens
        assert len(itens) == 1 and itens[0].questao.tipo == "discursiva"


def test_atividade_travada_cadastra_mas_nao_inclui(cliente_web, fabrica_sessao, prova):
    p = prova  # a atividade da prova já tem folhas geradas
    assert f"/questoes/nova?atividade={p['atividade']}" not in cliente_web.get(f"/atividades/{p['atividade']}").text
    dados = {"enunciado": "Nova", "correta": "B", "atividade_id": str(p["atividade"]),
             **{f"alternativa_{l}": l for l in "ABCDE"}}
    r = cliente_web.post("/questoes", data=dados, follow_redirects=False)
    assert "n%C3%A3o%20entrou%20na%20atividade" in r.headers["location"]
    with fabrica_sessao() as s:
        assert s.query(Questao).filter_by(enunciado="Nova").count() == 1
        assert len(s.get(Atividade, p["atividade"]).itens) == 3


def test_sem_atividade_o_cadastro_vai_para_a_questao(cliente_web):
    dados = {"enunciado": "Solta", "correta": "C", **{f"alternativa_{l}": l for l in "ABCDE"}}
    r = cliente_web.post("/questoes", data=dados, follow_redirects=False)
    assert r.headers["location"].startswith("/questoes/")
    assert "será incluída" not in cliente_web.get("/questoes/nova?atividade=9999").text
