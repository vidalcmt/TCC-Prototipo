"""Aceite ou ajuste da nota (RF09 a RF11), concordância e exportação das revisões."""

import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.database import obter_sessao
from app.main import app
from app.metricas.resumo import resumo_concordancia, resumo_requisicoes
from app.models import Correcao, MetricaRequisicao, Questao, RevisaoProfessor, Submissao
from app.revisao.servico import RevisaoInvalida, registrar_revisao


def criar_correcao(sessao, nota_sugerida=6.5, usou=True, nota_maxima=10.0):
    q = Questao(tipo="discursiva", enunciado="Explique.", nota_maxima=nota_maxima)
    sessao.add(q)
    sessao.flush()
    s = Submissao(questao_id=q.id, resposta_aluno="Resposta.", codigo_corpus="R001", origem="autor")
    sessao.add(s)
    sessao.flush()
    c = Correcao(submissao_id=s.id, questao_id=q.id, feedback_json="{}", nota_sugerida=nota_sugerida,
                 usou_resposta_esperada=usou, modelo="gpt-6.1-sol", prompt_versao="discursiva_v1")
    sessao.add(c)
    sessao.commit()
    return c


# ---------- regra de negócio ----------

def test_aceitar_grava_as_duas_notas_e_marca_aceite(sessao):
    c = criar_correcao(sessao)
    r = registrar_revisao(sessao, c, 6.5, "  Concordo  ")
    assert (r.nota_sugerida, r.nota_final, r.aceitou_sugestao) == (6.5, 6.5, True)
    assert r.comentario == "Concordo"


def test_ajustar_marca_que_houve_ajuste(sessao):
    c = criar_correcao(sessao)
    r = registrar_revisao(sessao, c, 8.0)
    assert r.aceitou_sugestao is False and r.nota_final == 8.0 and r.nota_sugerida == 6.5
    assert r.comentario is None


def test_digitar_a_mesma_nota_conta_como_aceite(sessao):
    c = criar_correcao(sessao)
    assert registrar_revisao(sessao, c, 6.5).aceitou_sugestao is True


@pytest.mark.parametrize("nota", [-0.5, 10.5])
def test_nota_fora_do_intervalo_e_recusada(sessao, nota):
    c = criar_correcao(sessao)
    with pytest.raises(RevisaoInvalida, match="entre 0 e 10"):
        registrar_revisao(sessao, c, nota)
    assert sessao.query(RevisaoProfessor).count() == 0


def test_segunda_revisao_da_mesma_correcao_e_recusada(sessao):
    c = criar_correcao(sessao)
    registrar_revisao(sessao, c, 6.5)
    with pytest.raises(RevisaoInvalida, match="já foi revisada"):
        registrar_revisao(sessao, c, 9.0)
    assert sessao.query(RevisaoProfessor).one().nota_final == 6.5


def test_banco_impede_duas_revisoes_mesmo_sem_a_checagem(sessao):
    c = criar_correcao(sessao)
    sessao.add_all([RevisaoProfessor(correcao_id=c.id, nota_sugerida=6.5, nota_final=6.5, aceitou_sugestao=True),
                    RevisaoProfessor(correcao_id=c.id, nota_sugerida=6.5, nota_final=7.0, aceitou_sugestao=False)])
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        sessao.commit()


def test_correcao_sem_nota_sugerida_nao_e_revisada(sessao):
    c = criar_correcao(sessao, nota_sugerida=None)
    with pytest.raises(RevisaoInvalida, match="não tem nota sugerida"):
        registrar_revisao(sessao, c, 5.0)


# ---------- resumos ----------

def test_concordancia_e_desvio_por_condicao(sessao):
    registrar_revisao(sessao, criar_correcao(sessao, 6.5, usou=False), 6.5)   # aceita
    registrar_revisao(sessao, criar_correcao(sessao, 6.5, usou=False), 8.5)   # +2
    registrar_revisao(sessao, criar_correcao(sessao, 7.0, usou=True), 6.0)    # -1
    todas, sem, com = resumo_concordancia(sessao)

    assert (todas.revisoes, todas.aceitas) == (3, 1)
    assert todas.taxa_concordancia == pytest.approx(1 / 3)
    assert todas.desvio_medio == pytest.approx(1 / 3)          # (0 + 2 - 1) / 3
    assert todas.desvio_absoluto_medio == pytest.approx(1.0)   # (0 + 2 + 1) / 3
    assert (sem.revisoes, sem.taxa_concordancia) == (2, 0.5)
    assert (com.revisoes, com.taxa_concordancia, com.desvio_medio) == (1, 0.0, -1.0)


def test_resumo_vazio_nao_divide_por_zero(sessao):
    todas = resumo_concordancia(sessao)[0]
    assert todas.revisoes == 0 and todas.taxa_concordancia is None and todas.desvio_medio is None
    assert resumo_requisicoes(sessao)[0].taxa_falha is None


def test_resumo_de_requisicoes_por_tipo(sessao):
    sessao.add_all([
        MetricaRequisicao(tipo_questao="discursiva", modelo_solicitado="m", prompt_versao="p",
                          latencia_ms=4000, sucesso=True, custo_usd=0.01),
        MetricaRequisicao(tipo_questao="discursiva", modelo_solicitado="m", prompt_versao="p",
                          latencia_ms=9000, sucesso=False, custo_usd=0.03),
    ])
    sessao.commit()
    discursivas = resumo_requisicoes(sessao)[1]
    assert (discursivas.total, discursivas.falhas, discursivas.taxa_falha) == (2, 1, 0.5)
    assert discursivas.custo_medio == pytest.approx(0.02)
    assert discursivas.latencia_media_ms == 4000  # só as com sucesso


# ---------- páginas ----------

@pytest.fixture
def cliente_web(fabrica_sessao):
    def sessao_de_teste():
        with fabrica_sessao() as s:
            yield s

    app.dependency_overrides[obter_sessao] = sessao_de_teste
    yield TestClient(app)
    app.dependency_overrides.clear()


def pagina_com_correcao(fabrica_sessao):
    from app.correcao.contratos import AnaliseCriterio, CorrecaoDiscursiva
    with fabrica_sessao() as s:
        c = criar_correcao(s)
        c.feedback_json = CorrecaoDiscursiva(
            questao_id=str(c.questao_id), usou_resposta_esperada=True, nota_sugerida=6.5, nota_maxima=10,
            confianca="media", feedback_elaborado="Feedback.",
            analise_criterios=[AnaliseCriterio(criterio="C1", peso=10, status="parcial",
                                               justificativa="J.", trecho_citado=None)],
        ).model_dump_json()
        s.commit()
        return c.id, c.submissao_id


def test_pagina_mostra_formulario_e_nota_pendente(fabrica_sessao, cliente_web):
    cid, sid = pagina_com_correcao(fabrica_sessao)
    pagina = cliente_web.get(f"/respostas/{sid}")
    assert "Pendente" in pagina.text and "Aceitar a nota sugerida (6,5)" in pagina.text
    # "Registrar outra nota" vem antes de "Aceitar": é o botão acionado pela tecla Enter
    assert pagina.text.index('value="ajustar"') < pagina.text.index('value="aceitar"')


def test_aceitar_pela_pagina(fabrica_sessao, cliente_web):
    cid, sid = pagina_com_correcao(fabrica_sessao)
    pagina = cliente_web.post(f"/correcoes/{cid}/revisao", data={"acao": "aceitar", "comentario": "Ok"})
    assert "Nota final do professor" in pagina.text and "Sugestão aceita" in pagina.text
    assert "Sua decisão sobre a nota" not in pagina.text  # formulário some depois da decisão


def test_ajustar_pela_pagina_aceita_virgula(fabrica_sessao, cliente_web):
    cid, sid = pagina_com_correcao(fabrica_sessao)
    pagina = cliente_web.post(f"/correcoes/{cid}/revisao", data={"acao": "ajustar", "nota_final": "8,5"})
    assert "Ajustada de 6,5 para 8,5 (+2)" in pagina.text
    with fabrica_sessao() as s:
        assert s.query(RevisaoProfessor).one().nota_final == 8.5


@pytest.mark.parametrize("dados, mensagem", [
    ({"acao": "ajustar", "nota_final": ""}, "Informe a nota final"),
    ({"acao": "ajustar", "nota_final": "11"}, "entre 0 e 10"),
    ({"acao": "aceitar", "nota_final": "9"}, "Você digitou outra nota"),
])
def test_erros_da_revisao_voltam_para_a_pagina_sem_gravar(fabrica_sessao, cliente_web, dados, mensagem):
    cid, sid = pagina_com_correcao(fabrica_sessao)
    pagina = cliente_web.post(f"/correcoes/{cid}/revisao", data=dados)
    assert mensagem in pagina.text
    with fabrica_sessao() as s:
        assert s.query(RevisaoProfessor).count() == 0


def test_segunda_decisao_pela_pagina_e_recusada(fabrica_sessao, cliente_web):
    cid, sid = pagina_com_correcao(fabrica_sessao)
    cliente_web.post(f"/correcoes/{cid}/revisao", data={"acao": "aceitar"})
    pagina = cliente_web.post(f"/correcoes/{cid}/revisao", data={"acao": "ajustar", "nota_final": "2"})
    with fabrica_sessao() as s:
        assert s.query(RevisaoProfessor).one().nota_final == 6.5
    assert "Sugestão aceita" in pagina.text


def test_metricas_mostram_concordancia_e_exportam_revisoes(fabrica_sessao, cliente_web):
    cid, sid = pagina_com_correcao(fabrica_sessao)
    cliente_web.post(f"/correcoes/{cid}/revisao", data={"acao": "ajustar", "nota_final": "7,5"})

    pagina = cliente_web.get("/metricas")
    assert "Concordância entre modelo e professor" in pagina.text and "+1,00" in pagina.text

    linhas = list(csv.DictReader(io.StringIO(cliente_web.get("/metricas/revisoes.csv").text)))
    assert len(linhas) == 1
    assert linhas[0]["nota_sugerida"] == "6.5" and linhas[0]["nota_final"] == "7.5"
    assert linhas[0]["aceitou_sugestao"] == "False" and linhas[0]["diferenca"] == "1.0"
    assert linhas[0]["codigo_corpus"] == "R001" and linhas[0]["usou_resposta_esperada"] == "True"
