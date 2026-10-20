"""Geração da explicação de questões objetivas e páginas de questões."""

import pytest
from fastapi.testclient import TestClient

from app.correcao.contratos import CorrecaoObjetiva, ExplicacaoAlternativa
from app.correcao.objetiva import campos_do_prompt, gerar_explicacao
from app.database import obter_sessao
from app.main import app
from app.models import Alternativa, Correcao, MetricaRequisicao, Questao
from app.questoes.router import obter_cliente_llm
from tests.falsos import ClienteFalso, resposta_falsa

LETRAS = "ABCDE"


def criar_questao(sessao, gabarito="D"):
    q = Questao(
        tipo="objetiva", enunciado="Texto-base sobre a Lei Maria da Penha.",
        area="ciencias-humanas", fonte="ENEM 2023, questão 60", ano=2023,
        alternativas=[Alternativa(letra=l, texto=f"Alternativa {l}", correta=l == gabarito) for l in LETRAS],
    )
    sessao.add(q)
    sessao.commit()
    return q


def saida_valida(questao_id, gabarito="D", letras=LETRAS, marcadas=None):
    marcadas = marcadas if marcadas is not None else [gabarito]
    return CorrecaoObjetiva(
        questao_id=str(questao_id),
        alternativa_correta=gabarito,
        explicacoes=[
            ExplicacaoAlternativa(letra=l, correta=l in marcadas, por_que=f"Raciocínio sobre {l}.",
                                  conceito_envolvido="violência patrimonial")
            for l in letras
        ],
        explicacao_correta="Passo 1. Passo 2.",
        nivel_dificuldade_estimado="medio",
    )


# ---------- geração ----------

def test_prompt_leva_enunciado_alternativas_e_gabarito(sessao):
    q = criar_questao(sessao)
    campos = campos_do_prompt(q)
    assert campos["gabarito"] == "D"
    assert "A) Alternativa A" in campos["alternativas"] and "E) Alternativa E" in campos["alternativas"]

    cliente = ClienteFalso(resposta_falsa(saida_valida(q.id)))
    gerar_explicacao(sessao, q, cliente=cliente)
    mensagem = cliente.chamadas[0]["input"][1]["content"]
    assert "Lei Maria da Penha" in mensagem and "informada pelo professor: D" in mensagem
    assert cliente.chamadas[0]["text_format"] is CorrecaoObjetiva


def test_saida_valida_grava_correcao_ligada_a_metrica(sessao):
    q = criar_questao(sessao)
    resultado = gerar_explicacao(sessao, q, cliente=ClienteFalso(resposta_falsa(saida_valida(q.id))))

    assert resultado.sucesso
    c = sessao.query(Correcao).one()
    m = sessao.query(MetricaRequisicao).one()
    assert m.correcao_id == c.id and m.sucesso and m.tipo_questao == "objetiva"
    assert c.prompt_versao == "objetiva_v1" and c.modelo == "gpt-6.1-sol"
    assert c.submissao_id is None
    assert CorrecaoObjetiva.model_validate_json(c.feedback_json).alternativa_correta == "D"


@pytest.mark.parametrize("saida, trecho_do_motivo", [
    (lambda qid: saida_valida(qid, gabarito="B", marcadas=["B"]), "diferente do gabarito"),
    (lambda qid: saida_valida(qid, letras="ABCD"), "alternativas explicadas"),
    (lambda qid: saida_valida(qid, marcadas=["D", "A"]), "marcadas como corretas"),
    (lambda qid: saida_valida(qid + 99), "questao_id"),
])
def test_saida_inconsistente_vira_falha_sem_correcao(sessao, saida, trecho_do_motivo):
    q = criar_questao(sessao)
    resultado = gerar_explicacao(sessao, q, cliente=ClienteFalso(resposta_falsa(saida(q.id))))

    assert not resultado.sucesso
    assert sessao.query(Correcao).count() == 0
    m = sessao.query(MetricaRequisicao).one()
    assert not m.sucesso and trecho_do_motivo in m.motivo_falha
    assert m.tokens_entrada == 1500  # tokens cobrados continuam registrados


def test_saida_malformada_vira_falha(sessao):
    q = criar_questao(sessao)
    resultado = gerar_explicacao(sessao, q, cliente=ClienteFalso(resposta_falsa(None, status="incomplete")))
    assert not resultado.sucesso
    assert sessao.query(Correcao).count() == 0
    assert "sem saida estruturada" in sessao.query(MetricaRequisicao).one().motivo_falha


# ---------- páginas ----------

@pytest.fixture
def cliente_web(fabrica_sessao):
    def sessao_de_teste():
        with fabrica_sessao() as s:
            yield s

    app.dependency_overrides[obter_sessao] = sessao_de_teste
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_lista_e_detalhe_mostram_a_questao_e_o_gabarito(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        qid = criar_questao(s).id

    lista = cliente_web.get("/questoes")
    assert lista.status_code == 200 and "ENEM 2023, questão 60" in lista.text

    detalhe = cliente_web.get(f"/questoes/{qid}")
    assert detalhe.status_code == 200
    assert "Lei Maria da Penha" in detalhe.text and "Gabarito" in detalhe.text
    assert "Gerar explicação" in detalhe.text


def test_questao_inexistente_responde_404(cliente_web):
    assert cliente_web.get("/questoes/999").status_code == 404


def test_cadastro_manual_grava_e_redireciona(fabrica_sessao, cliente_web):
    form = {"enunciado": "Qual a capital do Paraná?", "correta": "C", "area": "ciencias-humanas"}
    form.update({f"alternativa_{l}": f"Cidade {l}" for l in LETRAS})
    resposta = cliente_web.post("/questoes", data=form, follow_redirects=False)

    assert resposta.status_code == 303
    with fabrica_sessao() as s:
        q = s.query(Questao).one()
        assert q.fonte == "Cadastro manual"
        assert [a.letra for a in q.alternativas if a.correta] == ["C"]


def test_cadastro_incompleto_mostra_erros_e_nao_grava(fabrica_sessao, cliente_web):
    resposta = cliente_web.post("/questoes", data={"enunciado": "", "alternativa_A": "x"})
    assert resposta.status_code == 400
    assert "Preencha o enunciado" in resposta.text and "Indique qual alternativa" in resposta.text
    with fabrica_sessao() as s:
        assert s.query(Questao).count() == 0


def test_botao_gerar_mostra_explicacao_na_pagina(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        qid = criar_questao(s).id
    app.dependency_overrides[obter_cliente_llm] = lambda: ClienteFalso(resposta_falsa(saida_valida(qid)))

    pagina = cliente_web.post(f"/questoes/{qid}/explicar")
    assert pagina.status_code == 200
    assert "Raciocínio sobre A." in pagina.text and "violência patrimonial" in pagina.text
    assert "Caminho até a resposta" in pagina.text and "objetiva_v1" in pagina.text


def test_falha_na_geracao_aparece_com_o_motivo(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        qid = criar_questao(s).id
    app.dependency_overrides[obter_cliente_llm] = lambda: ClienteFalso(erro=ConnectionError("sem internet"))

    pagina = cliente_web.post(f"/questoes/{qid}/explicar")
    assert "Não foi possível gerar a explicação" in pagina.text
    assert "ConnectionError: sem internet" in pagina.text
