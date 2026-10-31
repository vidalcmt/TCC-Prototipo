"""Respostas por folha, nota de cada folha, correção em lote e liberação."""

import pytest

from app.config import config
from app.folhas.servico import gerar_folhas
from app.main import app
from app.models import (
    Alternativa, Atividade, AtividadeQuestao, Correcao, Folha, MetricaRequisicao, Questao, RevisaoProfessor,
    Submissao,
)
from app.questoes.cliente import obter_cliente_llm
from app.resultados import lote
from app.resultados.servico import (
    A_CORRIGIR, A_REVISAR, ANULADA, CERTA, EM_BRANCO, ERRADA, REVISADA, SEM_GABARITO, resultado_da_folha,
    visivel_para_o_aluno,
)
from tests.falsos import ClienteFalso, resposta_falsa
from tests.test_discursiva import RESPOSTA, criar_discursiva, saida


def _objetiva(correta="B", alternativas=True):
    return Questao(tipo="objetiva", enunciado="Objetiva.",
                   alternativas=[Alternativa(letra=l, texto=l, correta=l == correta) for l in "ABCDE"]
                   if alternativas else [])


@pytest.fixture
def prova(fabrica_sessao):
    """Atividade com duas objetivas (gabarito B) e uma discursiva de 10 pontos, e 3 folhas."""
    with fabrica_sessao() as s:
        o1, o2 = _objetiva(), _objetiva()
        s.add_all([o1, o2])
        d, corpus = criar_discursiva(s)
        a = Atividade(titulo="Prova", turma="3º A")
        s.add(a)
        s.flush()
        for ordem, q in enumerate([o1, o2, d], start=1):
            a.itens.append(AtividadeQuestao(questao_id=q.id, ordem=ordem))
        s.commit()
        folhas = gerar_folhas(s, a, 3, 8)
        return {"atividade": a.id, "o1": o1.id, "o2": o2.id, "d": d.id, "folhas": [f.id for f in folhas],
                "codigos": [f.codigo for f in folhas]}


def _url(p, i=0):
    return f"/atividades/{p['atividade']}/folhas/{p['folhas'][i]}"


def _resultado(fabrica_sessao, folha_id):
    with fabrica_sessao() as s:
        r = resultado_da_folha(s, s.get(Folha, folha_id))
        return {l.questao.id: l.situacao for l in r.linhas}, r.pontos, r.completa


def _cliente_falso(p, **kw):
    cliente = ClienteFalso(resposta_falsa(saida(p["d"], **kw)))
    app.dependency_overrides[obter_cliente_llm] = lambda: cliente
    return cliente


# ---------- registro das respostas ----------

def test_registrar_objetivas_e_discursiva(fabrica_sessao, cliente_web, prova):
    p = prova
    r = cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", f"q{p['o2']}": "multipla", f"q{p['d']}": RESPOSTA})
    assert "Respostas salvas." in r.text and "Certa" in r.text and "Anulada" in r.text
    situacoes, pontos, completa = _resultado(fabrica_sessao, p["folhas"][0])
    assert situacoes == {p["o1"]: CERTA, p["o2"]: ANULADA, p["d"]: A_CORRIGIR}
    assert pontos == 1 and not completa
    with fabrica_sessao() as s:
        sub = s.query(Submissao).filter_by(folha_id=p["folhas"][0], questao_id=p["o2"]).one()
        assert sub.alternativa_escolhida == "*" and sub.origem == "folha"


def test_objetiva_errada_e_em_branco(fabrica_sessao, cliente_web, prova):
    p = prova
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "C", f"q{p['o2']}": "branco", f"q{p['d']}": ""})
    situacoes, pontos, completa = _resultado(fabrica_sessao, p["folhas"][0])
    assert situacoes == {p["o1"]: ERRADA, p["o2"]: EM_BRANCO, p["d"]: EM_BRANCO}
    assert pontos == 0 and completa  # discursiva em branco vale zero sem chamar o modelo


def test_alternativa_invalida_nao_grava_nada(fabrica_sessao, cliente_web, prova):
    p = prova
    r = cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", f"q{p['o2']}": "Z"})
    assert "Questão 2: alternativa inválida." in r.text
    with fabrica_sessao() as s:
        assert s.query(Submissao).filter(Submissao.folha_id.is_not(None)).count() == 0


def test_salvar_e_ir_para_a_proxima(fabrica_sessao, cliente_web, prova):
    p = prova
    r = cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", "depois": "proxima"},
                         follow_redirects=False)
    assert r.headers["location"].startswith(_url(p, 1))
    assert "Folha 1: Respostas salvas." in cliente_web.get(r.headers["location"]).text


def test_objetiva_sem_gabarito_deixa_a_folha_pendente(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        q = _objetiva(alternativas=False)
        a = Atividade(titulo="X")
        s.add_all([q, a])
        s.flush()
        a.itens.append(AtividadeQuestao(questao_id=q.id, ordem=1))
        s.commit()
        folha = gerar_folhas(s, a, 1, 8)[0]
        aid, fid, qid = a.id, folha.id, q.id
    cliente_web.post(f"/atividades/{aid}/folhas/{fid}/respostas", data={f"q{qid}": "D"})
    situacoes, _, completa = _resultado(fabrica_sessao, fid)
    assert situacoes[qid] == SEM_GABARITO and not completa


def test_folha_de_outra_atividade_responde_404(fabrica_sessao, cliente_web, prova):
    with fabrica_sessao() as s:
        outra = Atividade(titulo="Outra")
        s.add(outra)
        s.commit()
        oid = outra.id
    assert cliente_web.get(f"/atividades/{oid}/folhas/{prova['folhas'][0]}").status_code == 404


# ---------- correção e revisão ----------

def test_corrigir_folha_revisar_e_concluir(fabrica_sessao, cliente_web, prova):
    p = prova
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", f"q{p['o2']}": "A", f"q{p['d']}": RESPOSTA})
    cliente = _cliente_falso(p, usou=True)
    r = cliente_web.post(f"{_url(p)}/corrigir")
    assert "Correção concluída." in r.text and "Revisar a nota" in r.text
    assert len(cliente.chamadas) == 1
    situacoes, pontos, _ = _resultado(fabrica_sessao, p["folhas"][0])
    assert situacoes[p["d"]] == A_REVISAR and pontos == 1
    with fabrica_sessao() as s:
        correcao = s.query(Correcao).one()
        assert correcao.usou_resposta_esperada  # usa a resposta esperada quando existe
        cid, sid = correcao.id, correcao.submissao_id

    pagina = cliente_web.get(f"/respostas/{sid}").text
    assert f'href="{_url(p)}#discursivas"' in pagina and p["codigos"][0] in pagina
    cliente_web.post(f"/correcoes/{cid}/revisao", data={"acao": "ajustar", "nota_final": "8"})
    situacoes, pontos, completa = _resultado(fabrica_sessao, p["folhas"][0])
    assert situacoes[p["d"]] == REVISADA and pontos == 9 and completa


def test_falha_do_modelo_mantem_pendente(fabrica_sessao, cliente_web, prova):
    p = prova
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['d']}": RESPOSTA})
    _cliente_falso(p, usou=False)  # condição trocada: saída inconsistente
    assert "1 de 1 correções falharam" in cliente_web.post(f"{_url(p)}/corrigir").text
    assert _resultado(fabrica_sessao, p["folhas"][0])[0][p["d"]] == A_CORRIGIR
    with fabrica_sessao() as s:
        assert s.query(MetricaRequisicao).filter_by(sucesso=False).count() == 1


def test_discursiva_corrigida_nao_e_alterada(fabrica_sessao, cliente_web, prova):
    p = prova
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "A", f"q{p['d']}": RESPOSTA})
    _cliente_falso(p)
    cliente_web.post(f"{_url(p)}/corrigir")
    r = cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", f"q{p['d']}": "Outro texto."})
    assert "Questão 3: a resposta já foi corrigida e não foi alterada." in r.text
    assert "readonly" in r.text
    with fabrica_sessao() as s:
        subs = {x.questao_id: x for x in s.query(Submissao).filter_by(folha_id=p["folhas"][0])}
        assert subs[p["d"]].resposta_aluno == RESPOSTA and subs[p["o1"]].alternativa_escolhida == "B"


# ---------- correção em lote ----------

def _responder_todas(cliente_web, p, n=3):
    for i in range(n):
        cliente_web.post(f"{_url(p, i)}/respostas", data={f"q{p['o1']}": "B", f"q{p['o2']}": "B", f"q{p['d']}": RESPOSTA})


def test_correcao_em_lote(fabrica_sessao, cliente_web, prova):
    p = prova
    _responder_todas(cliente_web, p)
    cliente = _cliente_falso(p)
    r = cliente_web.post(f"/atividades/{p['atividade']}/resultados/corrigir", follow_redirects=False)
    assert r.status_code == 303
    lote.aguardar(p["atividade"])
    assert len(cliente.chamadas) == 3
    painel = cliente_web.get(f"/atividades/{p['atividade']}/resultados").text
    assert "Última correção em lote: 3 de 3 corrigidas." in painel
    with fabrica_sessao() as s:
        assert s.query(Correcao).count() == 3
    # nada mais a corrigir
    r = cliente_web.post(f"/atividades/{p['atividade']}/resultados/corrigir")
    assert "Não há respostas discursivas esperando correção." in r.text


def test_lote_para_no_limite_diario(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    _responder_todas(cliente_web, p)
    _cliente_falso(p)
    monkeypatch.setattr(config, "limite_chamadas_dia", 2)
    cliente_web.post(f"/atividades/{p['atividade']}/resultados/corrigir", follow_redirects=False)
    lote.aguardar(p["atividade"])
    estado = lote.andamento(p["atividade"])
    assert estado.feitas == 2 and "Limite diário" in estado.mensagem and not estado.em_andamento


# ---------- painel, liberação e regras da atividade ----------

def test_painel_e_busca_pelo_codigo(fabrica_sessao, cliente_web, prova):
    p = prova
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", f"q{p['o2']}": "B", f"q{p['d']}": ""})
    painel = cliente_web.get(f"/atividades/{p['atividade']}/resultados").text
    assert "Concluída" in painel and "<strong>2</strong> de 12" in painel and "Digitar respostas" in painel
    digitado = p["codigos"][1].replace("-", "").lower()
    r = cliente_web.get(f"/atividades/{p['atividade']}/resultados?codigo={digitado}", follow_redirects=False)
    assert r.headers["location"] == _url(p, 1)
    assert "Nenhuma folha desta atividade tem o código" in cliente_web.get(
        f"/atividades/{p['atividade']}/resultados?codigo=AAAA-AAAA").text


def test_liberar_e_recolher(fabrica_sessao, cliente_web, prova):
    p = prova
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", f"q{p['o2']}": "B", f"q{p['d']}": ""})
    cliente_web.post(f"{_url(p, 1)}/respostas", data={f"q{p['o1']}": "B"})
    assert "Resultados liberados." in cliente_web.post(f"/atividades/{p['atividade']}/resultados/liberar").text
    with fabrica_sessao() as s:
        assert s.get(Atividade, p["atividade"]).resultados_liberados_em is not None
        completa, incompleta = (resultado_da_folha(s, s.get(Folha, f)) for f in p["folhas"][:2])
        assert visivel_para_o_aluno(completa) and not visivel_para_o_aluno(incompleta)
    cliente_web.post(f"/atividades/{p['atividade']}/resultados/recolher")
    with fabrica_sessao() as s:
        assert s.get(Atividade, p["atividade"]).resultados_liberados_em is None
        assert not visivel_para_o_aluno(resultado_da_folha(s, s.get(Folha, p["folhas"][0])))


@pytest.mark.parametrize("valor, esperado, mensagem", [
    ("2,5", 2.5, "Valor das objetivas atualizado."), ("0", 1.0, "maior que 0"), ("abc", 1.0, "maior que 0"),
])
def test_valor_das_objetivas(fabrica_sessao, cliente_web, prova, valor, esperado, mensagem):
    p = prova
    r = cliente_web.post(f"/atividades/{p['atividade']}/resultados/valor", data={"valor_objetiva": valor})
    assert mensagem in r.text
    with fabrica_sessao() as s:
        assert s.get(Atividade, p["atividade"]).valor_objetiva == esperado


def test_folhas_com_respostas_nao_podem_ser_descartadas(fabrica_sessao, cliente_web, prova):
    p = prova
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B"})
    assert "Descartar folhas" not in cliente_web.get(f"/atividades/{p['atividade']}").text
    r = cliente_web.post(f"/atividades/{p['atividade']}/folhas/descartar")
    assert "não podem ser descartadas" in r.text
    with fabrica_sessao() as s:
        assert s.query(Folha).count() == 3


def test_painel_avisa_objetiva_sem_gabarito(fabrica_sessao, cliente_web, prova):
    with fabrica_sessao() as s:
        for alt in s.get(Questao, prova["o2"]).alternativas:
            alt.correta = False
        s.commit()
    painel = cliente_web.get(f"/atividades/{prova['atividade']}/resultados").text
    assert "A questão 2 não tem alternativa correta cadastrada." in painel
