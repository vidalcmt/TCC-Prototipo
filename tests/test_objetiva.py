"""Geração da explicação de questões objetivas e páginas de questões."""

import pytest
from fastapi.testclient import TestClient

from app.correcao.contratos import (
    CorrecaoObjetiva, CorrecaoObjetivaV2, CorrecaoObjetivaV3, ExplicacaoAlternativa, ExplicacaoAlternativaV2,
    ExplicacaoAlternativaV3,
)
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


def saida_valida(questao_id, gabarito="D", letras=LETRAS, marcadas=None, tipo_na_correta=None,
                 tipo_nas_erradas="conceito_trocado", pista_na_correta=None):
    """Saída da versão 3, em uso. A alternativa B fica sem pista, como o prompt permite."""
    marcadas = marcadas if marcadas is not None else [gabarito]
    return CorrecaoObjetivaV3(
        questao_id=str(questao_id),
        alternativa_correta=gabarito,
        pista_do_enunciado="A expressão 'violência patrimonial' situa a questão na Lei Maria da Penha.",
        explicacoes=[
            ExplicacaoAlternativaV3(
                letra=l, correta=l in marcadas,
                tipo_de_erro=tipo_na_correta if l in marcadas else tipo_nas_erradas,
                explicacao=f"Explicação sobre {l}.",
                pista=pista_na_correta if l in marcadas else (None if l == "B" else f"Pista para eliminar {l}."),
                conceito_envolvido="violência patrimonial",
            )
            for l in letras
        ],
        explicacao_correta="Passo 1. Passo 2.",
        nivel_dificuldade_estimado="medio",
    )


def saida_v2(questao_id, gabarito="D", letras=LETRAS, marcadas=None, tipo_na_correta=None,
             tipo_nas_erradas="conceito_trocado"):
    marcadas = marcadas if marcadas is not None else [gabarito]
    return CorrecaoObjetivaV2(
        questao_id=str(questao_id),
        alternativa_correta=gabarito,
        explicacoes=[
            ExplicacaoAlternativaV2(
                letra=l, correta=l in marcadas,
                tipo_de_erro=tipo_na_correta if l in marcadas else tipo_nas_erradas,
                elemento_incorreto=None if l in marcadas else f"Confunde o conceito em {l}.",
                por_que=f"Raciocínio sobre {l}.",
                como_verificar=f"Como verificar {l}.",
                conceito_envolvido="violência patrimonial",
            )
            for l in letras
        ],
        explicacao_correta="Passo 1. Passo 2.",
        nivel_dificuldade_estimado="medio",
    )


def saida_v1(questao_id, gabarito="D"):
    return CorrecaoObjetiva(
        questao_id=str(questao_id), alternativa_correta=gabarito,
        explicacoes=[ExplicacaoAlternativa(letra=l, correta=l == gabarito, por_que=f"V1 sobre {l}.",
                                           conceito_envolvido="conceito v1") for l in LETRAS],
        explicacao_correta="Caminho v1.", nivel_dificuldade_estimado="baixo",
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
    assert cliente.chamadas[0]["text_format"] is CorrecaoObjetivaV3


def test_saida_valida_grava_correcao_ligada_a_metrica(sessao):
    q = criar_questao(sessao)
    resultado = gerar_explicacao(sessao, q, cliente=ClienteFalso(resposta_falsa(saida_valida(q.id))))

    assert resultado.sucesso
    c = sessao.query(Correcao).one()
    m = sessao.query(MetricaRequisicao).one()
    assert m.correcao_id == c.id and m.sucesso and m.tipo_questao == "objetiva"
    assert m.questao_id == q.id and m.submissao_id is None
    assert c.prompt_versao == "objetiva_v3" and c.modelo == "gpt-6.1-sol"
    assert c.submissao_id is None
    lida = CorrecaoObjetivaV3.model_validate_json(c.feedback_json)
    assert lida.alternativa_correta == "D" and "Lei Maria da Penha" in lida.pista_do_enunciado
    assert lida.explicacoes[0].tipo_de_erro == "conceito_trocado"
    assert lida.explicacoes[1].pista is None


@pytest.mark.parametrize("saida, trecho_do_motivo", [
    (lambda qid: saida_valida(qid, gabarito="B", marcadas=["B"]), "diferente do gabarito"),
    (lambda qid: saida_valida(qid, letras="ABCD"), "alternativas explicadas"),
    (lambda qid: saida_valida(qid, marcadas=["D", "A"]), "marcadas como corretas"),
    (lambda qid: saida_valida(qid + 99), "questao_id"),
    (lambda qid: saida_valida(qid, tipo_na_correta="anacronismo"), "alternativa correta D com tipo_de_erro"),
    (lambda qid: saida_valida(qid, tipo_nas_erradas=None), "sem tipo_de_erro"),
    (lambda qid: saida_valida(qid, pista_na_correta="Pista."), "alternativa correta D com pista"),
])
def test_saida_inconsistente_vira_falha_sem_correcao(sessao, saida, trecho_do_motivo):
    q = criar_questao(sessao)
    resultado = gerar_explicacao(sessao, q, cliente=ClienteFalso(resposta_falsa(saida(q.id))))

    assert not resultado.sucesso
    assert sessao.query(Correcao).count() == 0
    m = sessao.query(MetricaRequisicao).one()
    assert not m.sucesso and trecho_do_motivo in m.motivo_falha
    assert m.questao_id == q.id  # a origem fica registrada também na falha
    assert m.tokens_entrada == 1500  # tokens cobrados continuam registrados


def test_saida_malformada_vira_falha(sessao):
    q = criar_questao(sessao)
    resultado = gerar_explicacao(sessao, q, cliente=ClienteFalso(resposta_falsa(None, status="incomplete")))
    assert not resultado.sucesso
    assert sessao.query(Correcao).count() == 0
    assert "sem saida estruturada" in sessao.query(MetricaRequisicao).one().motivo_falha


# ---------- páginas ----------

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
    assert "Explicação sobre A." in pagina.text and "violência patrimonial" in pagina.text
    assert "Caminho até a resposta" in pagina.text and "objetiva_v3" in pagina.text
    assert "Conceitos confundidos" in pagina.text  # etiqueta do tipo de erro
    assert "Pista do enunciado" in pagina.text and "situa a questão na Lei Maria da Penha" in pagina.text
    assert "Pista para eliminar:" in pagina.text and "Pista para eliminar A." in pagina.text
    assert pagina.text.count("Pista para eliminar:") == 3  # A, C e E; B sem pista; D é a correta
    assert "O que está errado:" not in pagina.text and "Como perceber sem o gabarito" not in pagina.text


def test_explicacao_da_v2_continua_legivel(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        q = criar_questao(s)
        s.add(Correcao(questao_id=q.id, feedback_json=saida_v2(q.id).model_dump_json(),
                       modelo="gpt-6.1-sol", prompt_versao="objetiva_v2"))
        s.commit()
        qid = q.id
    pagina = cliente_web.get(f"/questoes/{qid}")
    assert "O que está errado:" in pagina.text and "Confunde o conceito em A." in pagina.text
    assert "Como perceber sem o gabarito:" in pagina.text and "Pista do enunciado" not in pagina.text


def test_explicacao_antiga_da_v1_continua_legivel(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        q = criar_questao(s)
        s.add(Correcao(questao_id=q.id, feedback_json=saida_v1(q.id).model_dump_json(),
                       modelo="gpt-6.1-sol", prompt_versao="objetiva_v1"))
        s.commit()
        qid = q.id

    pagina = cliente_web.get(f"/questoes/{qid}")
    assert pagina.status_code == 200
    assert "V1 sobre A." in pagina.text and "Caminho v1." in pagina.text
    assert "Como perceber sem o gabarito" not in pagina.text


def test_falha_na_geracao_aparece_com_o_motivo(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        qid = criar_questao(s).id
    app.dependency_overrides[obter_cliente_llm] = lambda: ClienteFalso(erro=ConnectionError("sem internet"))

    pagina = cliente_web.post(f"/questoes/{qid}/explicar")
    assert "Não foi possível gerar a explicação" in pagina.text
    assert "ConnectionError: sem internet" in pagina.text
