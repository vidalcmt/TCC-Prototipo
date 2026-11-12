"""Leitura da escrita com o Google Document AI e comparação com o Vision."""

import json

import cv2
import httpx
import numpy as np
import pytest

from app.config import config
from app.folhas import layout as L
from app.leitura import documentai, ocr
from app.leitura import lote as lote_leitura
from app.models import Atividade, LeituraPagina
from tests.folha_sintetica import desenhar, digitalizar
from tests.test_resultados import _LinhaSincrona, _url, prova  # noqa: F401

PROCESSADOR = "projects/devolutiva-1/locations/us/processors/abc123"


def _documento(palavras):
    """Documento no formato do Document AI: texto inteiro e tokens com trechos e posição normalizada."""
    texto, tokens = "", []
    for palavra, x_mm, y_mm, quebra in palavras:
        inicio = len(texto)
        texto += palavra + " "
        x, y = x_mm / L.LARGURA, y_mm / L.ALTURA
        token = {"layout": {"textAnchor": {"textSegments": [{"startIndex": str(inicio), "endIndex": str(len(texto))}]},
                            "boundingPoly": {"normalizedVertices": [{"x": x - 0.01, "y": y - 0.003}, {"x": x + 0.01, "y": y - 0.003},
                                                                    {"x": x + 0.01, "y": y + 0.003}, {"x": x - 0.01, "y": y + 0.003}]}}}
        if quebra:
            token["detectedBreak"] = {"type": quebra}
        tokens.append(token)
    tokens[0]["layout"]["textAnchor"]["textSegments"][0].pop("startIndex")  # o Google omite o zero
    return {"text": texto, "pages": [{"tokens": tokens}]}


@pytest.fixture(autouse=True)
def configuracao(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "documentai_processador", PROCESSADOR)
    monkeypatch.setattr(config, "pasta_arquivos", tmp_path)
    monkeypatch.setattr(documentai, "_token", lambda: "token-de-teste")
    monkeypatch.setattr(lote_leitura.threading, "Thread", _LinhaSincrona)


def _caixa():
    from tests.test_leitura import _layout
    return _layout(0, 1)[0].caixas[0]


def test_palavras_do_documento_em_milimetros_e_na_ordem_da_pauta():
    c = _caixa()
    documento = _documento([("linha.", c.x + 40, c.y + 13, ""), ("Segunda", c.x + 10, c.y + 13, ""),
                            ("A", c.x + 5, c.y + 5, ""), ("primei-", c.x + 15, c.y + 5, "HYPHEN"),
                            ("ra", c.x + 5, c.y + 13.5, "")])
    lista = documentai.palavras(documento)
    assert lista[0][0] == "linha." and abs(lista[0][2] - (c.x + 40)) < 0.01 and abs(lista[0][3] - (c.y + 13)) < 0.01
    assert ocr.textos_das_palavras(lista, [c]) == {f"q{c.questao_id}": "A primeira Segunda linha."}


def test_palavra_repetida_no_mesmo_lugar_fica_uma_vez():
    c = _caixa()
    documento = _documento([("o", c.x + 5, c.y + 5, ""), ("o", c.x + 5.4, c.y + 5, ""),
                            ("meio", c.x + 20, c.y + 5, ""), ("rneio", c.x + 20.5, c.y + 5.2, ""),
                            ("é", c.x + 35, c.y + 5, "")])
    tokens = documento["pages"][0]["tokens"]
    for token, confianca in zip(tokens, (0.9, 0.8, 0.7, 0.95, 0.9)):
        token["layout"]["confidence"] = confianca
    assert ocr.textos_das_palavras(documentai.palavras(documento), [c]) == {f"q{c.questao_id}": "o rneio é"}


def test_palavras_vizinhas_nao_sao_descartadas():
    c = _caixa()
    documento = _documento([("de", c.x + 5, c.y + 5, ""), ("de", c.x + 15, c.y + 5, ""), ("um", c.x + 25, c.y + 5, "")])
    assert ocr.textos_das_palavras(documentai.palavras(documento), [c]) == {f"q{c.questao_id}": "de de um"}


def test_pedido_ao_document_ai():
    pedidos = []

    def responder(pedido):
        pedidos.append(pedido)
        return httpx.Response(200, json={"document": _documento([("Olá", 30, 60, "")])})

    with httpx.Client(transport=httpx.MockTransport(responder)) as http:
        lista, latencia = documentai.palavras_da_pagina(np.full((100, 70), 255, np.uint8), http)
    pedido = pedidos[0]
    assert str(pedido.url) == f"https://us-documentai.googleapis.com/v1/{PROCESSADOR}:process"
    assert pedido.headers["authorization"] == "Bearer token-de-teste"
    corpo = json.loads(pedido.content)
    assert corpo["rawDocument"]["mimeType"] == "image/jpeg"
    assert corpo["processOptions"]["ocrConfig"]["hints"]["languageHints"] == ["pt"]
    assert lista[0][0] == "Olá" and latencia >= 0


@pytest.mark.parametrize("status, corpo, trecho", [
    (403, {"error": {"status": "PERMISSION_DENIED", "message": "denied"}}, "Usuário da API Document AI"),
    (404, {"error": {"status": "NOT_FOUND", "message": "processor"}}, "DOCUMENTAI_PROCESSADOR"),
    (403, {"error": {"status": "PERMISSION_DENIED", "message": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}}, "não tem permissão"),
])
def test_erros_explicados(status, corpo, trecho):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=corpo))) as http:
        with pytest.raises(ocr.OcrFalhou, match=trecho):
            documentai.processar(np.full((10, 10), 255, np.uint8), http)


def test_processador_mal_escrito(monkeypatch):
    monkeypatch.setattr(config, "documentai_processador", "abc123")
    with pytest.raises(ocr.OcrIndisponivel, match="projects/PROJETO"):
        documentai.processar(np.full((10, 10), 255, np.uint8))


def test_servico_escolhido_pela_configuracao(monkeypatch):
    c = _caixa()
    monkeypatch.setattr(documentai, "palavras_da_pagina",
                        lambda img, http=None: ([("Document", "", c.x + 5, c.y + 5), ("AI", "", c.x + 30, c.y + 5)], 700.0))
    monkeypatch.setattr(ocr, "anotar", lambda img, http=None: ({"pages": []}, 300.0))
    monkeypatch.setattr(config, "leitura_servico", "documentai")
    assert ocr.disponivel() and ocr.nome_do_servico() == "Google Document AI"
    assert ocr.transcrever(None, 12, [c]) == ({f"q{c.questao_id}": "Document AI"}, 700.0, "google-document-ai")
    monkeypatch.setattr(config, "leitura_servico", "vision")
    assert ocr.transcrever(None, 12, [c])[2] == "google-cloud-vision"


def test_leitura_pela_tela_com_document_ai_e_comparacao(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    monkeypatch.setattr(config, "leitura_servico", "documentai")
    with fabrica_sessao() as s:
        atividade = s.get(Atividade, p["atividade"])
        pagina = L.montar(atividade, atividade.linhas_por_resposta)[0]
    caixa = pagina.caixas[0]
    imagem = digitalizar(desenhar(pagina, p["codigos"][0], {p["o1"]: "B"}), angulo=1.0, semente=8)
    cliente_web.post(f"/atividades/{p['atividade']}/digitalizacoes",
                     files=[("arquivos", ("f.png", cv2.imencode(".png", imagem)[1].tobytes(), "image/png"))])
    leitura_da = [("Houve", "", caixa.x + 10, caixa.y + 4), ("êxodo", "", caixa.x + 30, caixa.y + 4),
                  ("rural.", "", caixa.x + 10, caixa.y + 12)]
    monkeypatch.setattr(documentai, "palavras_da_pagina", lambda img, http=None: (leitura_da, 900.0))
    assert "Google Document AI" in cliente_web.get(f"/atividades/{p['atividade']}/digitalizacoes").text
    r = cliente_web.post(f"{_url(p)}/ler")
    assert ">Houve êxodo rural.</textarea>" in r.text
    with fabrica_sessao() as s:
        assert s.query(LeituraPagina).one().servico_ocr == "google-document-ai"

    # o professor salva; a comparação lê a página de novo com os dois serviços
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", f"q{p['o2']}": "branco",
                                                     f"q{p['d']}": "Houve êxodo rural."})
    monkeypatch.setattr(ocr, "anotar", lambda img, http=None: ({"pages": [{"blocks": [{"paragraphs": [{"words": [
        {"symbols": [{"text": c} for c in "Houve"], "boundingBox": {"vertices": [
            {"x": (caixa.x + 10) * 12, "y": (caixa.y + 4) * 12}]}},
    ]}]}]}]}, 400.0))
    from scripts.comparar_ocr import comparar, resumo
    with fabrica_sessao() as s:
        somas, linhas = comparar(s)
    assert somas["documentai"]["campos"] == 1 and somas["documentai"]["cer"] == 0
    assert somas["vision"]["campos"] == 1 and somas["vision"]["cer"] > 0.5  # só leu "Houve"
    assert "documentai: 1 campos, CER médio 0.0%" in resumo(somas)
    assert {l["servico"] for l in linhas} == {"vision", "documentai"}

    # com a revisão da IA, cada serviço ganha uma segunda condição, contra a mesma referência
    from app.correcao.contratos import RevisaoTranscricaoV1
    from tests.falsos import ClienteFalso, resposta_falsa
    cliente = ClienteFalso(resposta_falsa(RevisaoTranscricaoV1(texto="Houve êxodo rural.", alteracoes=[],
                                                              trechos_incertos=[])))
    with fabrica_sessao() as s:
        somas, linhas = comparar(s, revisao=True, cliente=cliente)
        assert comparar(s, sem_texto=True)[1] == []  # nenhuma página conferida sem o texto lido
    assert set(somas) == {"vision", "documentai", "vision+revisao", "documentai+revisao"}
    assert somas["documentai+revisao"]["cer"] == 0 and len(cliente.chamadas) == 2
    # no Vision, que só leu "Houve", a revisão mudaria demais o texto: é descartada e fica o OCR
    assert somas["vision+revisao"]["cer"] == somas["vision"]["cer"]
