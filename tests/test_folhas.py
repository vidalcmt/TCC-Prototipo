"""Folhas de resposta: códigos únicos, trava das questões e layout fixo."""

import re

import pytest

from app.folhas import layout as L
from app.folhas.servico import ALFABETO, normalizar_codigo, novo_codigo
from app.models import Alternativa, Atividade, AtividadeQuestao, Folha, ItemQuestao, Questao


def _objetiva(n):
    return Questao(tipo="objetiva", enunciado=f"Objetiva {n}.",
                   alternativas=[Alternativa(letra=l, texto=l, correta=l == "B") for l in "ABCDE"])


def _discursiva(n, itens=0):
    return Questao(tipo="discursiva", enunciado=f"Discursiva {n}.", nota_maxima=5,
                   itens=[ItemQuestao(letra=l, enunciado=f"Item {l}.") for l in "abc"[:itens]])


def _atividade(fabrica_sessao, questoes):
    with fabrica_sessao() as s:
        a = Atividade(titulo="Prova de História", turma="3º A")
        s.add(a)
        s.add_all(questoes)
        s.flush()
        for ordem, q in enumerate(questoes, start=1):
            a.itens.append(AtividadeQuestao(questao_id=q.id, ordem=ordem))
        s.commit()
        return a.id, [q.id for q in questoes]


# ---------- códigos ----------

def test_codigo_tem_formato_e_alfabeto_sem_ambiguidade():
    codigos = {novo_codigo() for _ in range(500)}
    assert len(codigos) == 500
    for c in codigos:
        assert re.fullmatch(rf"[{ALFABETO}]{{4}}-[{ALFABETO}]{{4}}", c)
    assert not set("01ILO") & set("".join(codigos))


@pytest.mark.parametrize("digitado", ["abcd-efgh", " ABCD EFGH ", "abcdefgh"])
def test_codigo_digitado_e_normalizado(digitado):
    assert normalizar_codigo(digitado) == "ABCD-EFGH"


# ---------- geração e trava ----------

def test_gerar_folhas_e_mais_folhas_depois(fabrica_sessao, cliente_web):
    aid, _ = _atividade(fabrica_sessao, [_objetiva(1), _discursiva(2)])
    r = cliente_web.post(f"/atividades/{aid}/folhas", data={"quantidade": "30", "linhas": "12"})
    assert "30 folhas geradas (números 1 a 30)." in r.text
    r = cliente_web.post(f"/atividades/{aid}/folhas", data={"quantidade": "5", "linhas": "5"})
    assert "5 folhas geradas (números 31 a 35)." in r.text
    with fabrica_sessao() as s:
        a = s.get(Atividade, aid)
        assert [f.numero for f in a.folhas] == list(range(1, 36))
        assert len({f.codigo for f in a.folhas}) == 35
        assert a.linhas_por_resposta == 12  # a segunda geração não muda o layout


@pytest.mark.parametrize("dados, erro", [
    ({"quantidade": "0", "linhas": "8"}, "de 1 a 200"),
    ({"quantidade": "201", "linhas": "8"}, "de 1 a 200"),
    ({"quantidade": "10", "linhas": "99"}, "linhas por resposta vão de 1 a"),
])
def test_geracao_invalida(fabrica_sessao, cliente_web, dados, erro):
    aid, _ = _atividade(fabrica_sessao, [_objetiva(1)])
    assert erro in cliente_web.post(f"/atividades/{aid}/folhas", data=dados).text
    with fabrica_sessao() as s:
        assert s.query(Folha).count() == 0


def test_atividade_sem_questoes_nao_gera_folhas(fabrica_sessao, cliente_web):
    aid, _ = _atividade(fabrica_sessao, [])
    assert "Adicione questões" in cliente_web.post(f"/atividades/{aid}/folhas", data={"quantidade": "3"}).text


def test_questoes_travadas_depois_das_folhas_e_liberadas_ao_descartar(fabrica_sessao, cliente_web):
    aid, (q1, q2) = _atividade(fabrica_sessao, [_objetiva(1), _objetiva(2)])
    with fabrica_sessao() as s:
        extra = _objetiva(3)
        s.add(extra)
        s.commit()
        q3 = extra.id
    cliente_web.post(f"/atividades/{aid}/folhas", data={"quantidade": "2", "linhas": "8"})

    for url, dados in [(f"/atividades/{aid}/questoes", {"questao_id": q3}),
                       (f"/atividades/{aid}/questoes/{q2}/mover", {"direcao": "cima"}),
                       (f"/atividades/{aid}/questoes/{q1}/remover", {})]:
        assert "já foram geradas" in cliente_web.post(url, data=dados).text
    with fabrica_sessao() as s:
        assert [i.questao_id for i in s.get(Atividade, aid).itens] == [q1, q2]
    pagina = cliente_web.get(f"/atividades/{aid}").text
    assert "Remover" not in pagina and "Adicionar questões" not in pagina

    cliente_web.post(f"/atividades/{aid}/folhas/descartar")
    cliente_web.post(f"/atividades/{aid}/questoes/{q2}/mover", data={"direcao": "cima"})
    with fabrica_sessao() as s:
        assert s.query(Folha).count() == 0
        assert [i.questao_id for i in s.get(Atividade, aid).itens] == [q2, q1]


# ---------- impressão ----------

def test_folhas_impressas_com_codigo_qr_e_canhoto(fabrica_sessao, cliente_web):
    aid, _ = _atividade(fabrica_sessao, [_objetiva(1), _objetiva(2), _discursiva(3, itens=2)])
    cliente_web.post(f"/atividades/{aid}/folhas", data={"quantidade": "3", "linhas": "8"})
    html = cliente_web.get(f"/atividades/{aid}/folhas/imprimir").text
    with fabrica_sessao() as s:
        codigos = [f.codigo for f in s.get(Atividade, aid).folhas]
        primeira = s.get(Atividade, aid).folhas[0].id
    for c in codigos:
        assert html.count(c) >= 2  # no cabeçalho e no canhoto
    assert html.count('class="pagina"') == 3  # uma página por folha nesta atividade
    assert html.count("<svg") == 6 and html.count('class="marca"') == 12  # QR da folha e do canhoto
    assert html.count('class="bolha"') == 30 and html.count('class="caixa"') == 6
    assert "Nome" not in html and "/resultado" in html

    uma = cliente_web.get(f"/atividades/{aid}/folhas/imprimir?folha={primeira}").text
    assert uma.count('class="pagina"') == 1 and codigos[0] in uma and codigos[1] not in uma


def test_caderno_com_folhas_sai_sem_linhas(fabrica_sessao, cliente_web):
    aid, _ = _atividade(fabrica_sessao, [_discursiva(1)])
    assert '<div class="linhas">' in cliente_web.get(f"/atividades/{aid}/imprimir").text
    cliente_web.post(f"/atividades/{aid}/folhas", data={"quantidade": "1", "linhas": "8"})
    caderno = cliente_web.get(f"/atividades/{aid}/imprimir").text
    assert '<div class="linhas">' not in caderno and "responda na sua folha de respostas" in caderno


def test_imprimir_sem_folhas_responde_404(fabrica_sessao, cliente_web):
    aid, _ = _atividade(fabrica_sessao, [_objetiva(1)])
    assert cliente_web.get(f"/atividades/{aid}/folhas/imprimir").status_code == 404


# ---------- layout ----------

def _caixa_dentro(x0, y0, x1, y1):
    return L.AREA_X0 - 0.01 <= x0 and x1 <= L.AREA_X1 + 0.01 and L.AREA_Y0 - 0.01 <= y0 and y1 <= L.AREA_Y1 + 0.01


def _montar(fabrica_sessao, questoes, linhas=8):
    aid, _ = _atividade(fabrica_sessao, questoes)
    with fabrica_sessao() as s:
        return L.montar(s.get(Atividade, aid), linhas)


def test_layout_dentro_da_area_e_sem_sobreposicao(fabrica_sessao):
    paginas = _montar(fabrica_sessao, [_objetiva(n) for n in range(1, 11)] + [_discursiva(11, 3), _discursiva(12)])
    for p in paginas:
        for b in p.bolhas:
            assert _caixa_dentro(b.x - b.r, b.y - b.r, b.x + b.r, b.y + b.r)
        for c in p.caixas:
            assert _caixa_dentro(c.x, c.y - L.ROTULO_SECAO, c.x + c.largura, c.y + c.altura)
        elementos = [(b.x - b.r, b.y - b.r, b.x + b.r, b.y + b.r) for b in p.bolhas] + \
                    [(c.x, c.y, c.x + c.largura, c.y + c.altura) for c in p.caixas]
        for i, a in enumerate(elementos):
            for b in elementos[i + 1:]:
                assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b)
    assert sum(len(p.caixas) for p in paginas) == 4 and sum(len(p.bolhas) for p in paginas) == 50


def test_muitas_objetivas_usam_duas_colunas_e_nova_pagina(fabrica_sessao):
    paginas = _montar(fabrica_sessao, [_objetiva(n) for n in range(1, 61)])
    por_pagina = [len({b.numero for b in p.bolhas}) for p in paginas]
    assert len(paginas) == 2 and sum(por_pagina) == 60
    assert len({round(b.x) for b in paginas[0].bolhas if b.letra == "A"}) == 2  # duas colunas


def test_discursivas_quebram_pagina_quando_nao_cabem(fabrica_sessao):
    paginas = _montar(fabrica_sessao, [_discursiva(n) for n in range(1, 5)], linhas=8)
    assert len(paginas) == 2 and [len(p.caixas) for p in paginas] == [2, 2]


@pytest.mark.parametrize("texto, esperado", [
    (L.conteudo_qr("ABCD-EFGH", 2), ("ABCD-EFGH", 2)),
    ("https://outro.site", None),
    ("DEVOLUTIVA|ABCD-EFGH|x", None),
])
def test_conteudo_do_qr(texto, esperado):
    assert L.ler_qr(texto) == esperado


def test_objetiva_sem_alternativas_cadastradas_recebe_a_a_e(fabrica_sessao):
    sem = Questao(tipo="objetiva", enunciado="Alternativas só no texto.")
    paginas = _montar(fabrica_sessao, [sem, _objetiva(2), _discursiva(3)])
    assert [b.letra for b in paginas[0].bolhas if b.numero == 1] == list("ABCDE")
    ultima = max(b.y + b.r for b in paginas[0].bolhas)
    assert paginas[0].caixas[0].y - L.ROTULO_SECAO > ultima  # a caixa começa abaixo da grade
