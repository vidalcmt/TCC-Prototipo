"""Atividades: criação, questões em ordem e folha de impressão."""

import re

import pytest

from app.models import (
    Alternativa, Atividade, AtividadeQuestao, CriterioRubrica, ItemQuestao, Questao, RespostaEsperada,
)


def _questoes(fabrica_sessao):
    """Uma objetiva (gabarito C), uma discursiva com itens e uma discursiva simples."""
    with fabrica_sessao() as s:
        objetiva = Questao(tipo="objetiva", enunciado="Enunciado objetivo sobre absolutismo.", fonte="ENEM 2023",
                           alternativas=[Alternativa(letra=l, texto=f"Texto {l}", correta=l == "C") for l in "ABCDE"])
        a, b = ItemQuestao(letra="a", enunciado="Comando do a."), ItemQuestao(letra="b", enunciado="Comando do b.")
        com_itens = Questao(tipo="discursiva", enunciado="Texto-base da Fuvest.", nota_maxima=5, itens=[a, b],
                            criterios=[CriterioRubrica(descricao="Critério do a", peso=2, item=a),
                                       CriterioRubrica(descricao="Critério do b", peso=3, item=b)],
                            resposta_esperada=RespostaEsperada(texto="Resposta esperada da Fuvest."))
        simples = Questao(tipo="discursiva", enunciado="Discursiva simples.", nota_maxima=10)
        s.add_all([objetiva, com_itens, simples])
        s.commit()
        return objetiva.id, com_itens.id, simples.id


def _criar_atividade(cliente, **dados):
    resposta = cliente.post("/atividades", data={"titulo": "Revisão de História", "turma": "3º A", **dados},
                            follow_redirects=False)
    assert resposta.status_code == 303
    return int(resposta.headers["location"].rsplit("/", 1)[1])


def _ordem(fabrica_sessao, atividade_id):
    with fabrica_sessao() as s:
        return [i.questao_id for i in s.get(Atividade, atividade_id).itens]


def test_criar_e_listar(fabrica_sessao, cliente_web):
    aid = _criar_atividade(cliente_web, instrucoes="Responda a caneta.")
    lista = cliente_web.get("/atividades").text
    assert "Revisão de História" in lista and "3º A" in lista and "0 questões" in lista
    assert 'href="/atividades"' in cliente_web.get("/").text  # aba na barra
    with fabrica_sessao() as s:
        a = s.get(Atividade, aid)
        assert a.instrucoes == "Responda a caneta." and a.usuario_id is not None


def test_titulo_obrigatorio(fabrica_sessao, cliente_web):
    resposta = cliente_web.post("/atividades", data={"titulo": " "})
    assert resposta.status_code == 400 and "Dê um título" in resposta.text


def test_adicionar_mover_e_remover(fabrica_sessao, cliente_web):
    q1, q2, q3 = _questoes(fabrica_sessao)
    aid = _criar_atividade(cliente_web)
    for q in (q1, q2, q3, q1):  # a repetida é ignorada
        cliente_web.post(f"/atividades/{aid}/questoes", data={"questao_id": q})
    assert _ordem(fabrica_sessao, aid) == [q1, q2, q3]

    cliente_web.post(f"/atividades/{aid}/questoes/{q3}/mover", data={"direcao": "cima"})
    assert _ordem(fabrica_sessao, aid) == [q1, q3, q2]
    cliente_web.post(f"/atividades/{aid}/questoes/{q1}/mover", data={"direcao": "cima"})  # já é a primeira
    assert _ordem(fabrica_sessao, aid) == [q1, q3, q2]

    cliente_web.post(f"/atividades/{aid}/questoes/{q1}/remover")
    assert _ordem(fabrica_sessao, aid) == [q3, q2]
    with fabrica_sessao() as s:
        assert [i.ordem for i in s.get(Atividade, aid).itens] == [1, 2]
        assert s.get(Questao, q1) is not None  # a questão continua cadastrada


def test_busca_para_adicionar_esconde_as_ja_incluidas(fabrica_sessao, cliente_web):
    q1, q2, q3 = _questoes(fabrica_sessao)
    aid = _criar_atividade(cliente_web)
    cliente_web.post(f"/atividades/{aid}/questoes", data={"questao_id": q1})
    pagina = cliente_web.get(f"/atividades/{aid}?tipo=").text
    assert "Busque por uma palavra" in pagina
    pagina = cliente_web.get(f"/atividades/{aid}?busca=enunciado").text
    assert f'name="questao_id" value="{q1}"' not in pagina
    pagina = cliente_web.get(f"/atividades/{aid}?tipo=discursiva").text
    assert f'name="questao_id" value="{q2}"' in pagina and f'name="questao_id" value="{q3}"' in pagina


def test_adicionar_volta_para_a_busca_so_dentro_da_atividade(fabrica_sessao, cliente_web):
    q1, _, _ = _questoes(fabrica_sessao)
    aid = _criar_atividade(cliente_web)
    r = cliente_web.post(f"/atividades/{aid}/questoes", data={"questao_id": q1, "voltar": "https://fora.com"},
                         follow_redirects=False)
    assert r.headers["location"] == f"/atividades/{aid}"
    assert cliente_web.post(f"/atividades/{aid}/questoes", data={"questao_id": "999"}).status_code == 400


def test_editar_e_excluir(fabrica_sessao, cliente_web):
    q1, _, _ = _questoes(fabrica_sessao)
    aid = _criar_atividade(cliente_web)
    cliente_web.post(f"/atividades/{aid}/questoes", data={"questao_id": q1})
    cliente_web.post(f"/atividades/{aid}/editar", data={"titulo": "Novo título", "turma": "", "instrucoes": "X"})
    with fabrica_sessao() as s:
        a = s.get(Atividade, aid)
        assert (a.titulo, a.turma, a.instrucoes) == ("Novo título", None, "X")
    cliente_web.post(f"/atividades/{aid}/excluir")
    with fabrica_sessao() as s:
        assert s.get(Atividade, aid) is None and s.query(AtividadeQuestao).count() == 0
        assert s.get(Questao, q1) is not None
    assert cliente_web.get(f"/atividades/{aid}").status_code == 404


def _atividade_completa(fabrica_sessao, cliente_web):
    q1, q2, q3 = _questoes(fabrica_sessao)
    aid = _criar_atividade(cliente_web, instrucoes="Responda a caneta.")
    for q in (q2, q1, q3):
        cliente_web.post(f"/atividades/{aid}/questoes", data={"questao_id": q})
    return aid


def test_folha_do_aluno(fabrica_sessao, cliente_web):
    aid = _atividade_completa(fabrica_sessao, cliente_web)
    folha = cliente_web.get(f"/atividades/{aid}/imprimir").text
    assert "Nome:" in folha and "Responda a caneta." in folha and "impressao.css" in folha
    # ordem da atividade: discursiva com itens, objetiva, discursiva simples
    assert folha.index("Texto-base da Fuvest.") < folha.index("Enunciado objetivo") < folha.index("Discursiva simples.")
    assert "Questão 3" in folha and "(valor: 5 pontos)" in folha
    assert "Comando do a." in folha and "Comando do b." in folha
    assert folha.count('<span class="bolha">') == 5 and 'class="correta"' not in folha
    assert "Resposta esperada da Fuvest." not in folha and "Gabarito, uso do professor" not in folha
    # 8 linhas por padrão: duas respostas de item e uma resposta simples
    assert len(re.findall(r'<div class="linhas">', folha)) == 3
    assert folha.count("<div></div>") == 3 * 8


@pytest.mark.parametrize("linhas, esperado", [(12, 12), (99, 8)])
def test_numero_de_linhas(fabrica_sessao, cliente_web, linhas, esperado):
    aid = _atividade_completa(fabrica_sessao, cliente_web)
    folha = cliente_web.get(f"/atividades/{aid}/imprimir?linhas={linhas}").text
    assert folha.count("<div></div>") == 3 * esperado


def test_folha_com_gabarito(fabrica_sessao, cliente_web):
    aid = _atividade_completa(fabrica_sessao, cliente_web)
    folha = cliente_web.get(f"/atividades/{aid}/imprimir?gabarito=1").text
    assert "Gabarito, uso do professor" in folha and "Nome:" not in folha
    assert "<span>2: C</span>" in folha  # a objetiva é a questão 2 da folha
    assert folha.count('class="correta"') == 1
    assert "Resposta esperada da Fuvest." in folha and "Critério do b" in folha and "3 pontos" in folha
    assert '<div class="linhas">' not in folha
    assert "Não cadastrada." in folha  # discursiva simples sem resposta esperada


def test_atividades_exigem_login(cliente_anonimo):
    assert cliente_anonimo.get("/atividades", follow_redirects=False).status_code == 303
