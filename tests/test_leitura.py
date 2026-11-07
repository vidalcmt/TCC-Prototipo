"""Leitura automática: alinhamento, bolinhas, transcrição e conferência."""

import json
from types import SimpleNamespace as N

import cv2
import httpx
import numpy as np
import pytest

from app.config import config
from app.folhas import layout as L
from app.leitura import lote as lote_leitura
from app.leitura import ocr
from app.leitura.alinhamento import ESCALA, AlinhamentoFalhou, alinhar
from app.leitura.bolhas import ler_bolhas
from app.models import Atividade, LeituraPagina, Submissao
from scripts.medir_leitura import distancia, medir, taxa_de_erro
from tests.folha_sintetica import desenhar, digitalizar
from tests.test_resultados import _LinhaSincrona, _url, prova  # noqa: F401

ALTERNATIVAS = [N(letra=l) for l in "ABCDE"]


def _layout(n_objetivas=20, discursivas=0):
    itens = [N(questao=N(id=i, tipo="objetiva", alternativas=ALTERNATIVAS, itens=[])) for i in range(1, n_objetivas + 1)]
    itens += [N(questao=N(id=100 + i, tipo="discursiva", alternativas=[], itens=[])) for i in range(discursivas)]
    return L.montar(N(itens=itens), 8)


# ---------- alinhamento e bolinhas ----------

MARCAS = {1: "A", 2: "B", 3: ["C", "D"], 4: ("x", "E"), 7: "E", 20: "C"}
ESPERADO = {q: "branco" for q in range(1, 21)} | {1: "A", 2: "B", 3: "multipla", 4: "E", 7: "E", 20: "C"}


@pytest.mark.parametrize("angulo, perspectiva, girar, semente", [
    (0, 0.0, False, 1), (2.5, 0.015, False, 2), (-3, 0.02, False, 3), (1.5, 0.01, True, 4), (-2, 0.02, True, 5),
])
def test_bolinhas_lidas_em_digitalizacoes_imperfeitas(angulo, perspectiva, girar, semente):
    pagina = _layout()[0]
    imagem = digitalizar(desenhar(pagina, "ABCD-EFGH", MARCAS), angulo=angulo, perspectiva=perspectiva,
                         girar=girar, semente=semente)
    alinhada = alinhar(imagem)
    lidas = ler_bolhas(alinhada.imagem, pagina)
    assert {q: l.marcada for q, l in lidas.items()} == ESPERADO
    assert alinhada.girada == girar
    assert lidas[4].duvida  # um X não preenche a bolinha: o professor confere
    assert not lidas[1].duvida and not lidas[5].duvida


def test_pagina_sem_marcas_nao_e_alinhada():
    with pytest.raises(AlinhamentoFalhou):
        alinhar(np.full((2339, 1654), 255, np.uint8))


# ---------- transcrição ----------

def _palavra(texto, x_mm, y_mm, quebra="SPACE"):
    x, y = x_mm * ESCALA, y_mm * ESCALA
    simbolos = [{"text": c} for c in texto]
    simbolos[-1]["property"] = {"detectedBreak": {"type": quebra}}
    return {"boundingBox": {"vertices": [{"x": x - 10, "y": y - 5}, {"x": x + 10, "y": y - 5},
                                         {"x": x + 10, "y": y + 5}, {"x": x - 10, "y": y + 5}]},
            "symbols": simbolos}


def anotacao(palavras):
    return {"pages": [{"blocks": [{"paragraphs": [{"words": palavras}]}]}]}


def test_palavras_atribuidas_a_cada_caixa():
    caixas = _layout(0, 2)[0].caixas
    a, b = caixas
    texto = anotacao([
        _palavra("Questão", a.x + 5, a.y - 4),                      # rótulo impresso, fora da caixa
        _palavra("O", a.x + 10, a.y + 4), _palavra("êxodo", a.x + 20, a.y + 4),
        _palavra("rural", a.x + 40, a.y + 4, "EOL_SURE_SPACE"),
        _palavra("cresceu.", a.x + 10, a.y + 12, "LINE_BREAK"),
        _palavra("Não", b.x + 10, b.y + 4), _palavra("sei", b.x + 25, b.y + 4, "LINE_BREAK"),
    ])
    assert ocr.textos_por_caixa(texto, caixas) == {"q100": "O êxodo rural\ncresceu.", "q101": "Não sei"}


def test_chamada_ao_google_cloud_vision(monkeypatch):
    monkeypatch.setattr(config, "google_vision_api_key", "chave-de-teste")
    pedidos = []

    def responder(pedido):
        pedidos.append(pedido)
        return httpx.Response(200, json={"responses": [{"fullTextAnnotation": anotacao([])}]})

    with httpx.Client(transport=httpx.MockTransport(responder)) as http:
        resultado, latencia = ocr.anotar(np.full((100, 100), 255, np.uint8), http)
    corpo = json.loads(pedidos[0].content)["requests"][0]
    assert pedidos[0].url.params["key"] == "chave-de-teste"
    assert corpo["features"] == [{"type": "DOCUMENT_TEXT_DETECTION"}] and corpo["imageContext"]["languageHints"] == ["pt"]
    assert resultado == anotacao([]) and latencia >= 0


@pytest.mark.parametrize("status, corpo, mensagem", [
    (403, {"error": {"message": "API key not valid"}}, "API key not valid"),
    (200, {"responses": [{"error": {"message": "Bad image"}}]}, "Bad image"),
])
def test_erros_do_google_cloud_vision(monkeypatch, status, corpo, mensagem):
    monkeypatch.setattr(config, "google_vision_api_key", "x")
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=corpo))) as http:
        with pytest.raises(ocr.OcrFalhou, match=mensagem):
            ocr.anotar(np.full((10, 10), 255, np.uint8), http)


def test_sem_chave_a_escrita_nao_e_lida(monkeypatch):
    monkeypatch.setattr(config, "google_vision_api_key", "")
    with pytest.raises(ocr.OcrIndisponivel):
        ocr.anotar(np.full((10, 10), 255, np.uint8))


# ---------- fluxo completo pela tela ----------

@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "pasta_arquivos", tmp_path)
    monkeypatch.setattr(lote_leitura.threading, "Thread", _LinhaSincrona)
    lote_leitura._andamentos.clear()


def _enviar_folha(fabrica_sessao, cliente_web, p, marcas, com_ocr=True, monkeypatch=None):
    with fabrica_sessao() as s:
        atividade = s.get(Atividade, p["atividade"])
        pagina = L.montar(atividade, atividade.linhas_por_resposta)[0]
    imagem = digitalizar(desenhar(pagina, p["codigos"][0], marcas), angulo=1.2, semente=9)
    cliente_web.post(f"/atividades/{p['atividade']}/digitalizacoes",
                     files=[("arquivos", ("folha.png", cv2.imencode(".png", imagem)[1].tobytes(), "image/png"))])
    caixa = pagina.caixas[0]
    if com_ocr:
        monkeypatch.setattr(config, "google_vision_api_key", "x")
        monkeypatch.setattr(ocr, "anotar", lambda img, http=None: (anotacao([
            _palavra("Houve", caixa.x + 10, caixa.y + 4), _palavra("êxodo", caixa.x + 30, caixa.y + 4),
            _palavra("rural.", caixa.x + 50, caixa.y + 4, "LINE_BREAK")]), 850.0))
    return pagina


def test_ler_conferir_e_medir(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    _enviar_folha(fabrica_sessao, cliente_web, p, {p["o1"]: "B", p["o2"]: ("x", "C")}, monkeypatch=monkeypatch)
    r = cliente_web.post(f"/atividades/{p['atividade']}/digitalizacoes/ler")
    assert "Última leitura: 1 de 1 páginas lidas." in r.text

    pagina = cliente_web.get(_url(p)).text
    assert "Respostas lidas automaticamente" in pagina
    assert f'name="q{p["o1"]}" value="B" checked' in pagina and f'name="q{p["o2"]}" value="C" checked' in pagina
    assert ">confira</span>" in pagina  # o X da questão 2
    assert ">Houve êxodo rural.</textarea>" in pagina and f"/recorte/q{p['d']}" in pagina
    with fabrica_sessao() as s:
        assert s.query(Submissao).filter(Submissao.folha_id.is_not(None)).count() == 0  # nada gravado ainda
        leitura = s.query(LeituraPagina).one()
        assert leitura.servico_ocr == "google-cloud-vision" and leitura.latencia_ocr_ms == 850.0

    recorte = cliente_web.get(f"{_url(p)}/recorte/q{p['d']}")
    assert recorte.status_code == 200 and recorte.headers["content-type"] == "image/jpeg"

    # o professor confere: mantém as objetivas e corrige uma palavra da transcrição
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", f"q{p['o2']}": "C",
                                                     f"q{p['d']}": "Houve êxodo rural."})
    assert "Respostas lidas automaticamente" not in cliente_web.get(_url(p)).text
    with fabrica_sessao() as s:
        assert s.query(LeituraPagina).one().conferida_em is not None
        medida = medir(s)
    assert (medida.objetivas, medida.acertos, medida.duvidosas, medida.textos) == (2, 2, 1, 1)
    assert medida.soma_cer == 0
    assert "2 de 2 lidas corretamente (100.0%)" in medida.resumo()


def test_sem_chave_le_so_as_bolinhas(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    monkeypatch.setattr(config, "google_vision_api_key", "")
    _enviar_folha(fabrica_sessao, cliente_web, p, {p["o1"]: "A"}, com_ocr=False)
    assert "A leitura da escrita está desligada" in cliente_web.get(f"/atividades/{p['atividade']}/digitalizacoes").text
    r = cliente_web.post(f"{_url(p)}/ler")
    assert "Leitura concluída." in r.text and "GOOGLE_VISION_API_KEY" in r.text
    assert f'name="q{p["o1"]}" value="A" checked' in r.text and f'name="q{p["o2"]}" value="branco" checked' in r.text


def test_leitura_nao_muda_respostas_ja_salvas(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "D"})
    _enviar_folha(fabrica_sessao, cliente_web, p, {p["o1"]: "B"}, monkeypatch=monkeypatch)
    pagina = cliente_web.post(f"{_url(p)}/ler").text
    assert f'name="q{p["o1"]}" value="D" checked' in pagina and f'name="q{p["o1"]}" value="B" checked' not in pagina


def test_falha_de_alinhamento_aparece_na_folha(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    branca = np.full((2339, 1654), 255, np.uint8)
    cliente_web.post(f"/atividades/{p['atividade']}/digitalizacoes",
                     files=[("arquivos", ("branca.png", cv2.imencode(".png", branca)[1].tobytes(), "image/png"))])
    with fabrica_sessao() as s:
        from app.models import PaginaDigitalizada
        pid = s.query(PaginaDigitalizada).one().id
    cliente_web.post(f"/atividades/{p['atividade']}/digitalizacoes/{pid}/atribuir",
                     data={"codigo": p["codigos"][0], "pagina": "1"})
    r = cliente_web.post(f"{_url(p)}/ler")
    assert "1 de 1 páginas não puderam ser lidas" in r.text and "quatro marcas pretas" in r.text


# ---------- medida ----------

@pytest.mark.parametrize("a, b, d", [("casa", "casa", 0), ("casa", "cassa", 1), ("", "abc", 3), ("abc", "", 3),
                                     ("kitten", "sitting", 3)])
def test_distancia_de_edicao(a, b, d):
    assert distancia(a, b) == d


def test_taxas_de_erro():
    assert taxa_de_erro("o exodo  rural", "o êxodo rural") == pytest.approx(1 / 13)
    assert taxa_de_erro("o exodo rural", "o êxodo rural", por_palavra=True) == pytest.approx(1 / 3)
    assert taxa_de_erro("", "") == 0 and taxa_de_erro("x", "") == 1
