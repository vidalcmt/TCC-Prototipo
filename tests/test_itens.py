"""Questões discursivas com itens (a, b, c) e conferências da versão 2."""

import pytest

from app.correcao.contratos import (
    AnaliseCriterio, AnaliseCriterioV2, CorrecaoDiscursiva, CorrecaoDiscursivaV2, problemas_da_discursiva,
)
from app.correcao.discursiva import SEM_ITENS, campos_do_prompt, gerar_correcao
from app.main import app
from app.models import (
    Correcao, CriterioRubrica, ItemQuestao, MetricaRequisicao, Questao, RespostaItem, Submissao,
)
from app.questoes.cliente import obter_cliente_llm
from tests.falsos import ClienteFalso, resposta_falsa

RESPOSTA_A = "As mulheres eram vistas como ameaça porque controlavam o parto."
RESPOSTA_C = "Era uma época de muita religião."


def criar_questao_com_itens(sessao):
    """Modelo de questão da Fuvest: texto-base e três itens, rubrica 1/2/2, nota máxima 5."""
    a, b, c = (ItemQuestao(letra=letra, enunciado=f"Comando do item {letra}.") for letra in "abc")
    q = Questao(tipo="discursiva", enunciado="Texto-base sobre a caça às bruxas.", nota_maxima=5.0,
                itens=[a, b, c],
                criterios=[CriterioRubrica(descricao="Explica o alvo", peso=1, item=a),
                           CriterioRubrica(descricao="Dois elementos da crise", peso=2, item=b),
                           CriterioRubrica(descricao="Instituição e papel", peso=2, item=c)])
    sessao.add(q)
    sessao.flush()
    s = Submissao(questao_id=q.id, codigo_corpus="R010", resposta_aluno="",
                  respostas_itens=[RespostaItem(item=a, texto=RESPOSTA_A), RespostaItem(item=b, texto=""),
                                   RespostaItem(item=c, texto=RESPOSTA_C)])
    sessao.add(s)
    sessao.commit()
    return q, s


def saida_itens(questao_id, itens=("a", "b", "c"), trechos=("controlavam o parto", None, "muita religião"),
                status=("atendido", "nao_atendido", "parcial"), nota=2.0, confianca="alta"):
    # a atendido (1) + b não atendido (0) + c parcial (1) = 2 de 5 pontos de peso: 2/5 x 5 = 2,0.
    return CorrecaoDiscursivaV2(
        questao_id=str(questao_id), usou_resposta_esperada=False,
        analise_criterios=[
            AnaliseCriterioV2(criterio=f"Critério {i}", item=item, peso=peso, status=st,
                              justificativa="J.", trecho_citado=trecho)
            for i, (item, peso, st, trecho) in enumerate(zip(itens, (1, 2, 2), status, trechos), start=1)
        ],
        feedback_elaborado="No item c, o enunciado pede uma instituição e o seu papel.",
        nota_sugerida=nota, nota_maxima=5, confianca=confianca,
        motivo_confianca="Os itens b e c têm evidência clara.",
    )


# ---------- cadastro ----------

def _form(**extra):
    return {"enunciado": "Texto-base.", "nota_maxima": "5", **extra}


def test_cadastro_com_itens_e_criterios_por_item(fabrica_sessao, cliente_web):
    resposta = cliente_web.post("/questoes/discursivas", data=_form(
        item_a="Explique o alvo.", item_b="Cite dois elementos.", item_c="Identifique a instituição.",
        criterio_1="Explica o alvo", peso_1="1", criterio_item_1="a",
        criterio_2="Dois elementos", peso_2="2", criterio_item_2="b",
        criterio_3="Clareza geral", peso_3="1", criterio_item_3="",
    ), follow_redirects=False)
    assert resposta.status_code == 303
    with fabrica_sessao() as s:
        q = s.query(Questao).one()
        assert [(i.letra, i.enunciado) for i in q.itens] == [
            ("a", "Explique o alvo."), ("b", "Cite dois elementos."), ("c", "Identifique a instituição.")]
        assert [c.item.letra if c.item else None for c in q.criterios] == ["a", "b", None]


@pytest.mark.parametrize("extra, erro", [
    ({"item_a": "A.", "item_c": "C."}, "falta o item b"),
    ({"item_a": "A."}, "pelo menos dois"),
    ({"item_a": "A.", "item_b": "B.", "criterio_1": "X", "peso_1": "1", "criterio_item_1": "c"},
     "Critério 1: o item c não foi preenchido"),
    ({"criterio_1": "X", "peso_1": "1", "criterio_item_1": "a"}, "Critério 1: o item a não foi preenchido"),
])
def test_cadastro_com_itens_invalidos(fabrica_sessao, cliente_web, extra, erro):
    resposta = cliente_web.post("/questoes/discursivas", data=_form(**extra))
    assert resposta.status_code == 400 and erro in resposta.text
    with fabrica_sessao() as s:
        assert s.query(Questao).count() == 0


# ---------- resposta por item ----------

def test_resposta_com_um_campo_por_item(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        qid = criar_questao_com_itens(s)[0].id
    pagina = cliente_web.get(f"/questoes/{qid}")
    assert 'name="resposta_a"' in pagina.text and 'name="resposta_c"' in pagina.text
    assert 'name="resposta_aluno"' not in pagina.text and "Comando do item b." in pagina.text

    resposta = cliente_web.post(f"/questoes/{qid}/respostas", data={
        "resposta_a": "Texto do a.", "resposta_b": "", "resposta_c": "Texto do c.", "codigo_corpus": "R011",
    }, follow_redirects=False)
    assert resposta.status_code == 303
    with fabrica_sessao() as s:
        sub = s.query(Submissao).filter_by(codigo_corpus="R011").one()
        assert [(r.item.letra, r.texto) for r in sub.respostas_itens] == [
            ("a", "Texto do a."), ("b", ""), ("c", "Texto do c.")]
        assert sub.resposta_aluno == "a) Texto do a.\n\nb) (em branco)\n\nc) Texto do c."

    pagina = cliente_web.get(resposta.headers["location"])
    assert "Texto do a." in pagina.text and "Em branco." in pagina.text


def test_resposta_vazia_em_todos_os_itens_e_recusada(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        qid = criar_questao_com_itens(s)[0].id
    assert cliente_web.post(f"/questoes/{qid}/respostas", data={"resposta_a": " "}).status_code == 400


# ---------- prompt ----------

def test_prompt_com_itens(sessao):
    q, s = criar_questao_com_itens(sessao)
    campos = campos_do_prompt(q, s, usar_resposta_esperada=False)
    assert campos["itens"] == "a) Comando do item a.\nb) Comando do item b.\nc) Comando do item c."
    assert "1. Explica o alvo (peso 1, item a)" in campos["rubrica"]
    assert campos["resposta_aluno"] == f"a) {RESPOSTA_A}\n\nb) (em branco)\n\nc) {RESPOSTA_C}"


def test_prompt_sem_itens_avisa_resposta_unica(sessao):
    q = Questao(tipo="discursiva", enunciado="E.", nota_maxima=10)
    sessao.add(q)
    sessao.flush()
    s = Submissao(questao_id=q.id, resposta_aluno="R.")
    sessao.add(s)
    sessao.commit()
    campos = campos_do_prompt(q, s, False)
    assert campos["itens"] == SEM_ITENS and campos["resposta_aluno"] == "R."


# ---------- conferências da versão 2 ----------

def _corrigir(sessao, q, s, saida):
    return gerar_correcao(sessao, s, usar_resposta_esperada=False, cliente=ClienteFalso(resposta_falsa(saida)))


def test_correcao_com_itens_valida(sessao):
    q, s = criar_questao_com_itens(sessao)
    resultado = _corrigir(sessao, q, s, saida_itens(q.id, nota=2.0))
    assert resultado.sucesso, resultado.metrica.motivo_falha
    assert sessao.query(Correcao).one().prompt_versao == "discursiva_v2"


@pytest.mark.parametrize("dados, motivo", [
    # trecho do item a citado num critério do item c
    ({"trechos": ("controlavam o parto", None, "controlavam o parto"), "nota": 2.0},
     "não existe na resposta do item c"),
    # trecho num item deixado em branco
    ({"trechos": ("controlavam o parto", "muita religião", "muita religião"), "nota": 2.0},
     "não existe na resposta do item b"),
    ({"itens": ("a", "b", "d"), "nota": 2.0}, "item 'd', que a questão não tem"),
    ({"itens": ("a", "c", "b"), "nota": 2.0}, "diferentes da rubrica"),
    ({"nota": 1.5}, "não corresponde aos critérios"),
])
def test_correcao_com_itens_inconsistente(sessao, dados, motivo):
    q, s = criar_questao_com_itens(sessao)
    resultado = _corrigir(sessao, q, s, saida_itens(q.id, **dados))
    assert not resultado.sucesso
    assert motivo in resultado.metrica.motivo_falha
    assert sessao.query(Correcao).count() == 0


def test_item_em_questao_sem_itens_e_inconsistente():
    saida = saida_itens(1, nota=2.0, trechos=(None, None, None))
    problemas = problemas_da_discursiva(saida, 1, "R.", False, 5, [1, 2, 2])
    assert any("em questão sem itens" in p for p in problemas)


@pytest.mark.parametrize("nota, aceita", [(3.5, True), (4.0, True), (3.0, False), (3.75, False)])
def test_nota_no_empate_aceita_os_dois_arredondamentos(nota, aceita):
    # Pesos iguais, atendido + parcial + dois não atendidos: 1,5 / 4 x 10 = 3,75.
    saida = CorrecaoDiscursivaV2(
        questao_id="1", usou_resposta_esperada=False, feedback_elaborado="F.", nota_sugerida=nota,
        nota_maxima=10, confianca="alta", motivo_confianca="M.",
        analise_criterios=[AnaliseCriterioV2(criterio=str(i), item=None, peso=1, status=st, justificativa="J.",
                                             trecho_citado=None)
                           for i, st in enumerate(["atendido", "parcial", "nao_atendido", "nao_atendido"])],
    )
    problemas = problemas_da_discursiva(saida, 1, "R.", False, 10, None)
    assert (problemas == []) is aceita


# ---------- página da resposta ----------

def test_pagina_separa_analise_do_professor_e_feedback_do_aluno(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        q, sub = criar_questao_com_itens(s)
        qid, sid = q.id, sub.id
    app.dependency_overrides[obter_cliente_llm] = lambda: ClienteFalso(resposta_falsa(saida_itens(qid, nota=2.0)))
    pagina = cliente_web.post(f"/respostas/{sid}/corrigir", data={"condicao": "sem"})
    assert "para o professor" in pagina.text and "para o aluno" in pagina.text
    assert "Confiança do modelo: alta: Os itens b e c têm evidência clara." in pagina.text
    assert '<span class="letra-item">c)</span> <strong>Critério 3</strong>' in pagina.text


def test_correcao_antiga_da_v1_continua_legivel(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        q = Questao(tipo="discursiva", enunciado="E.", nota_maxima=10)
        s.add(q)
        s.flush()
        sub = Submissao(questao_id=q.id, resposta_aluno="Resposta.")
        s.add(sub)
        s.flush()
        v1 = CorrecaoDiscursiva(
            questao_id=str(q.id), usou_resposta_esperada=False, feedback_elaborado="Feedback antigo.",
            nota_sugerida=5, nota_maxima=10, confianca="baixa",
            analise_criterios=[AnaliseCriterio(criterio="C", peso=10, status="parcial", justificativa="J.",
                                               trecho_citado=None)])
        s.add(Correcao(submissao_id=sub.id, questao_id=q.id, nota_sugerida=5, usou_resposta_esperada=False,
                       modelo="m", prompt_versao="discursiva_v1", feedback_json=v1.model_dump_json()))
        s.commit()
        sid = sub.id
    pagina = cliente_web.get(f"/respostas/{sid}")
    assert pagina.status_code == 200 and "Feedback antigo." in pagina.text
    assert "Confiança do modelo: baixa." in pagina.text


def test_metrica_da_v2_registra_tipo_e_prompt(sessao):
    q, s = criar_questao_com_itens(sessao)
    _corrigir(sessao, q, s, saida_itens(q.id, nota=2.0))
    m = sessao.query(MetricaRequisicao).one()
    assert m.tipo_questao == "discursiva" and m.prompt_versao == "discursiva_v2"
    assert m.questao_id == q.id and m.submissao_id == s.id
