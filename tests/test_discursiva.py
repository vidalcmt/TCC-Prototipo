"""Correção de questões discursivas e páginas de discursivas e respostas."""

import pytest
from fastapi.testclient import TestClient

from app.correcao.contratos import AnaliseCriterio, CorrecaoDiscursiva, trecho_existe
from app.correcao.discursiva import CondicaoIndisponivel, campos_do_prompt, gerar_correcao
from app.database import obter_sessao
from app.main import app
from app.models import Correcao, CriterioRubrica, MetricaRequisicao, Questao, RespostaEsperada, Submissao
from app.questoes.cliente import obter_cliente_llm
from tests.falsos import ClienteFalso, resposta_falsa

RESPOSTA = (
    "A Revolução Industrial provocou o êxodo rural, porque os camponeses perderam as terras "
    "comunais e foram para as cidades trabalhar nas fábricas."
)


def criar_discursiva(sessao, com_resposta_esperada=True, com_rubrica=True):
    q = Questao(tipo="discursiva", enunciado="Explique uma consequência social da Revolução Industrial.",
                area="ciencias-humanas", fonte="Vestibular de exemplo", nota_maxima=10.0)
    if com_rubrica:
        q.criterios = [CriterioRubrica(descricao="Identifica a consequência", peso=4.0),
                       CriterioRubrica(descricao="Explica a causa", peso=6.0)]
    if com_resposta_esperada:
        q.resposta_esperada = RespostaEsperada(texto="Êxodo rural e urbanização, pelos cercamentos.")
    s = Submissao(resposta_aluno=RESPOSTA, codigo_corpus="R001", origem="autor")
    sessao.add(q)
    sessao.flush()
    s.questao_id = q.id
    sessao.add(s)
    sessao.commit()
    return q, s


def saida(questao_id, usou=True, nota=8.0, nota_maxima=10.0, trecho="provocou o êxodo rural",
          pesos=(4.0, 6.0)):
    return CorrecaoDiscursiva(
        questao_id=str(questao_id), usou_resposta_esperada=usou,
        analise_criterios=[
            AnaliseCriterio(criterio=f"Critério {i}", peso=p, status="atendido" if i == 1 else "parcial",
                            justificativa=f"Justificativa {i}.", trecho_citado=trecho if i == 1 else None)
            for i, p in enumerate(pesos, start=1)
        ],
        feedback_elaborado="Você identificou bem a consequência; faltou explicar os cercamentos.",
        nota_sugerida=nota, nota_maxima=nota_maxima, confianca="alta",
    )


# ---------- trecho citado ----------

@pytest.mark.parametrize("trecho, existe", [
    ("provocou o êxodo rural", True),
    ("PROVOCOU   o Êxodo rural", True),                    # maiúsculas e espaços
    ("“foram para as cidades”", True),                      # aspas curvas
    ("A Revolução Industrial ... nas fábricas", True),      # reticências no meio
    ("nas fábricas ... A Revolução Industrial", False),     # ordem invertida
    ("provocou a urbanização", False),                      # paráfrase
])
def test_trecho_citado_precisa_existir_na_resposta(trecho, existe):
    assert trecho_existe(trecho, RESPOSTA) is existe


# ---------- montagem do prompt ----------

def test_prompt_com_resposta_esperada_e_rubrica(sessao):
    q, s = criar_discursiva(sessao)
    campos = campos_do_prompt(q, s, usar_resposta_esperada=True)
    assert "Êxodo rural e urbanização" in campos["resposta_esperada"]
    assert "1. Identifica a consequência (peso 4)" in campos["rubrica"]
    assert campos["usou_resposta_esperada"] == "true" and campos["nota_maxima"] == "10"


def test_prompt_sem_resposta_esperada_nao_vaza_a_resposta(sessao):
    q, s = criar_discursiva(sessao)
    campos = campos_do_prompt(q, s, usar_resposta_esperada=False)
    assert "Êxodo rural e urbanização" not in str(campos)
    assert "não informou resposta esperada" in campos["resposta_esperada"]
    assert campos["usou_resposta_esperada"] == "false"


def test_prompt_sem_rubrica_pede_criterios_ao_modelo(sessao):
    q, s = criar_discursiva(sessao, com_rubrica=False)
    assert "não informou rubrica" in campos_do_prompt(q, s, False)["rubrica"]


# ---------- geração ----------

@pytest.mark.parametrize("usar", [True, False])
def test_correcao_valida_grava_a_condicao_executada(sessao, usar):
    q, s = criar_discursiva(sessao)
    cliente = ClienteFalso(resposta_falsa(saida(q.id, usou=usar)))
    resultado = gerar_correcao(sessao, s, usar_resposta_esperada=usar, cliente=cliente)

    assert resultado.sucesso
    c = sessao.query(Correcao).one()
    m = sessao.query(MetricaRequisicao).one()
    assert c.usou_resposta_esperada is usar and m.usou_resposta_esperada is usar
    assert c.submissao_id == s.id and c.nota_sugerida == 8.0 and c.prompt_versao == "discursiva_v1"
    assert m.correcao_id == c.id and m.tipo_questao == "discursiva"
    # O texto do sistema também recebe a condição preenchida
    sistema = cliente.chamadas[0]["input"][0]["content"]
    assert ("true" if usar else "false") in sistema and "{" not in sistema


def test_condicao_com_resposta_esperada_exige_resposta_cadastrada(sessao):
    q, s = criar_discursiva(sessao, com_resposta_esperada=False)
    with pytest.raises(CondicaoIndisponivel):
        gerar_correcao(sessao, s, usar_resposta_esperada=True, cliente=ClienteFalso())
    assert sessao.query(MetricaRequisicao).count() == 0  # nada foi enviado ao modelo


@pytest.mark.parametrize("dados, motivo", [
    ({"usou": False}, "diferente da condição executada"),
    ({"nota": 11.0}, "fora do intervalo"),
    ({"nota": -1.0}, "fora do intervalo"),
    ({"nota_maxima": 100.0, "nota": 80.0}, "nota_maxima 100.0 diferente"),
    ({"trecho": "a crise do feudalismo"}, "não existe na resposta do aluno"),
    ({"pesos": (4.0, 3.0, 3.0)}, "a rubrica tem 2"),
    ({"pesos": (5.0, 5.0)}, "diferentes da rubrica"),
])
def test_correcao_inconsistente_vira_falha_sem_gravar(sessao, dados, motivo):
    q, s = criar_discursiva(sessao)
    resultado = gerar_correcao(sessao, s, usar_resposta_esperada=True,
                               cliente=ClienteFalso(resposta_falsa(saida(q.id, **dados))))
    assert not resultado.sucesso
    assert sessao.query(Correcao).count() == 0
    m = sessao.query(MetricaRequisicao).one()
    assert not m.sucesso and motivo in m.motivo_falha


def test_sem_rubrica_aceita_criterios_definidos_pelo_modelo(sessao):
    q, s = criar_discursiva(sessao, com_rubrica=False)
    resultado = gerar_correcao(sessao, s, False,
                               cliente=ClienteFalso(resposta_falsa(saida(q.id, usou=False, pesos=(3, 3, 4)))))
    assert resultado.sucesso


# ---------- páginas ----------

@pytest.fixture
def cliente_web(fabrica_sessao):
    def sessao_de_teste():
        with fabrica_sessao() as s:
            yield s

    app.dependency_overrides[obter_sessao] = sessao_de_teste
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_cadastro_com_rubrica_e_resposta_esperada(fabrica_sessao, cliente_web):
    form = {"enunciado": "Explique o êxodo rural.", "nota_maxima": "10,0",
            "resposta_esperada": "Migração do campo para a cidade.",
            "criterio_1": "Define o conceito", "peso_1": "4", "criterio_2": "Dá um exemplo", "peso_2": "6"}
    resposta = cliente_web.post("/questoes/discursivas", data=form, follow_redirects=False)
    assert resposta.status_code == 303

    with fabrica_sessao() as s:
        q = s.query(Questao).one()
        assert q.tipo == "discursiva" and q.nota_maxima == 10.0
        assert [(c.descricao, c.peso) for c in q.criterios] == [("Define o conceito", 4.0), ("Dá um exemplo", 6.0)]
        assert q.resposta_esperada.texto == "Migração do campo para a cidade."


def test_cadastro_sem_rubrica_nem_resposta_esperada(fabrica_sessao, cliente_web):
    resposta = cliente_web.post("/questoes/discursivas", data={"enunciado": "Explique.", "nota_maxima": "5"},
                                follow_redirects=False)
    assert resposta.status_code == 303
    with fabrica_sessao() as s:
        q = s.query(Questao).one()
        assert q.criterios == [] and q.resposta_esperada is None


def test_cadastro_invalido_mostra_erros(fabrica_sessao, cliente_web):
    resposta = cliente_web.post("/questoes/discursivas", data={
        "enunciado": "", "nota_maxima": "0", "criterio_1": "Sem peso", "peso_2": "3",
    })
    assert resposta.status_code == 400
    for erro in ["Preencha o enunciado", "nota máxima maior que zero",
                 "Critério 1: informe um peso", "Critério 2: falta a descrição"]:
        assert erro in resposta.text
    with fabrica_sessao() as s:
        assert s.query(Questao).count() == 0


def test_formulario_de_cadastro_abre(cliente_web):
    assert cliente_web.get("/questoes/nova-discursiva").status_code == 200


def test_pagina_da_questao_e_registro_de_resposta(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        qid = criar_discursiva(s)[0].id

    pagina = cliente_web.get(f"/questoes/{qid}")
    assert "Identifica a consequência" in pagina.text and "Êxodo rural e urbanização" in pagina.text
    assert "R001" in pagina.text

    nova = cliente_web.post(f"/questoes/{qid}/respostas",
                            data={"resposta_aluno": "Outra resposta.", "codigo_corpus": "R002", "origem": "voluntario"},
                            follow_redirects=False)
    assert nova.status_code == 303
    with fabrica_sessao() as s:
        sub = s.query(Submissao).filter_by(codigo_corpus="R002").one()
        assert sub.origem == "voluntario"


def test_lista_mostra_os_dois_tipos(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        criar_discursiva(s)
    assert "Discursiva" in cliente_web.get("/questoes").text


def test_corrigir_pela_pagina_mostra_nota_como_sugestao(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        q, sub = criar_discursiva(s)
        qid, sid = q.id, sub.id
    app.dependency_overrides[obter_cliente_llm] = lambda: ClienteFalso(resposta_falsa(saida(qid, usou=True)))

    pagina = cliente_web.post(f"/respostas/{sid}/corrigir", data={"condicao": "com"})
    assert pagina.status_code == 200
    assert "Nota sugerida pelo modelo" in pagina.text and "A nota final é do professor" in pagina.text
    assert "com resposta esperada" in pagina.text and "Atendido" in pagina.text and "Parcial" in pagina.text
    assert "provocou o êxodo rural" in pagina.text and "faltou explicar os cercamentos" in pagina.text


def test_corrigir_com_resposta_esperada_inexistente_responde_400(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        sid = criar_discursiva(s, com_resposta_esperada=False)[1].id
    app.dependency_overrides[obter_cliente_llm] = lambda: ClienteFalso()
    assert cliente_web.post(f"/respostas/{sid}/corrigir", data={"condicao": "com"}).status_code == 400


def test_falha_na_correcao_aparece_com_o_motivo(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        q, sub = criar_discursiva(s)
        qid, sid = q.id, sub.id
    app.dependency_overrides[obter_cliente_llm] = lambda: ClienteFalso(
        resposta_falsa(saida(qid, trecho="frase inventada")))
    pagina = cliente_web.post(f"/respostas/{sid}/corrigir", data={"condicao": "com"})
    assert "Não foi possível corrigir" in pagina.text and "não existe na resposta do aluno" in pagina.text


def test_botao_de_explicar_recusa_questao_discursiva(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        qid = criar_discursiva(s)[0].id
    assert cliente_web.post(f"/questoes/{qid}/explicar").status_code == 400
