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

def _palavra(texto, x_mm, y_mm, quebra="SPACE", escala=ESCALA):
    x, y = x_mm * escala, y_mm * escala
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
    assert ocr.textos_por_caixa(texto, caixas) == {"q100": "O êxodo rural cresceu.", "q101": "Não sei"}


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


enviadas: list = []


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
        def anotar_falso(img, http=None):
            enviadas.append(img.shape)
            e = ocr.ESCALA_OCR
            return anotacao([_palavra("Houve", caixa.x + 10, caixa.y + 4, escala=e),
                             _palavra("êxodo", caixa.x + 30, caixa.y + 4, escala=e),
                             _palavra("rural.", caixa.x + 50, caixa.y + 4, "LINE_BREAK", escala=e)]), 850.0
        monkeypatch.setattr(ocr, "anotar", anotar_falso)
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
    assert enviadas[-1] == (round(297 * ocr.ESCALA_OCR), round(210 * ocr.ESCALA_OCR))  # mais resolução para a escrita
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


# ---------- mensagens de erro e teste da chave ----------

@pytest.mark.parametrize("mensagem, trecho", [
    ("API key not valid. Please pass a valid API key.", "a chave está errada"),
    ("Cloud Vision API has not been used in project 123 before or it is disabled.", "não está ativada"),
    ("Requests to this API vision.googleapis.com method ... are blocked.", "não tem permissão"),
    ("The provided API key has an IP address restriction.", "restrita a outro endereço IP"),
    ("This API method requires billing to be enabled.", "faturamento"),
    ("Algo inesperado", "HTTP 500): Algo inesperado"),
])
def test_erros_explicados(mensagem, trecho):
    assert trecho in ocr.explicar_erro(500 if trecho.startswith("HTTP") else 403, mensagem)


def test_script_de_teste_da_chave(monkeypatch, capsys):
    from scripts import teste_vision

    monkeypatch.setattr(config, "google_vision_api_key", "")
    assert teste_vision.main([]) == 1 and "não está no .env" in capsys.readouterr().out

    monkeypatch.setattr(config, "google_vision_api_key", "AIzaChaveDeTesteXYZ1")
    monkeypatch.setattr(ocr, "anotar", lambda img: ({"text": "Devolutiva teste\n2026"}, 420.0))
    assert teste_vision.main([]) == 0
    saida = capsys.readouterr().out
    assert "Funcionou em 420 ms" in saida and "Lido pelo Vision:  Devolutiva teste 2026" in saida
    assert "AIzaChaveDeTeste" not in saida and "...XYZ1" in saida  # a chave não aparece

    def falhar(img):
        raise ocr.OcrFalhou(ocr.explicar_erro(400, "API key not valid."))
    monkeypatch.setattr(ocr, "anotar", falhar)
    assert teste_vision.main([]) == 1 and "a chave está errada" in capsys.readouterr().out


# ---------- sem as marcas dos cantos ----------

def _como_aplicativo(img, angulo=0.6, escala_y=0.985):
    """Imita um aplicativo de celular: folha recortada, levemente girada e esticada numa direção."""
    h, w = img.shape
    girada = cv2.warpAffine(img, cv2.getRotationMatrix2D((w / 2, h / 2), angulo, 1.0), (w, h), borderValue=255)
    esticada = cv2.resize(girada, (w, round(h * escala_y)), interpolation=cv2.INTER_AREA)
    ruido = np.random.default_rng(2).normal(0, 6, esticada.shape)
    return np.clip(esticada.astype(float) * 0.95 + 8 + ruido, 0, 255).astype(np.uint8)


@pytest.mark.parametrize("girar", [False, True])
def test_alinha_sem_as_marcas_pelo_qr_e_pelas_caixas(girar):
    from app.leitura.alinhamento import ELEMENTOS, erro_das_caixas
    pagina = _layout(0, 4)[0]
    escrita = {(c.questao_id, None): "Resposta escrita bem em cima da linha" for c in pagina.caixas}
    imagem = _como_aplicativo(desenhar(pagina, "ABCD-EFGH", escrita=escrita, com_marcas=False))
    if girar:
        imagem = cv2.rotate(imagem, cv2.ROTATE_180)
    alinhada = alinhar(imagem, pagina)
    assert alinhada.metodo == ELEMENTOS and alinhada.girada == girar
    assert len(pagina.caixas) == 2  # duas caixas de 8 linhas por página
    assert alinhada.caixas_usadas == 2 and alinhada.erro_mm < 1.0
    erro, conferidas = erro_das_caixas(alinhada.imagem, pagina)
    assert conferidas == 2 and erro < 1.0


def test_sem_marcas_e_sem_caixas_alinha_de_forma_aproximada():
    from app.leitura.alinhamento import APROXIMADO
    pagina = _layout()[0]  # só objetivas: não há caixas para usar
    imagem = _como_aplicativo(desenhar(pagina, "ABCD-EFGH", MARCAS, com_marcas=False), angulo=0)
    alinhada = alinhar(imagem, pagina)
    assert alinhada.metodo == APROXIMADO and alinhada.erro_mm is None


def test_com_marcas_o_erro_e_medido_nas_caixas():
    from app.leitura.alinhamento import MARCAS as PELAS_MARCAS
    pagina = _layout(0, 2)[0]
    alinhada = alinhar(digitalizar(desenhar(pagina, "ABCD-EFGH"), angulo=1.0, semente=4), pagina)
    assert alinhada.metodo == PELAS_MARCAS and alinhada.caixas_usadas == 2 and alinhada.erro_mm < 1.0


def test_leitura_sem_marcas_registra_o_metodo_e_avisa_quando_aproximada(fabrica_sessao, cliente_web, prova,
                                                                       monkeypatch):
    p = prova
    monkeypatch.setattr(config, "google_vision_api_key", "")
    with fabrica_sessao() as s:
        atividade = s.get(Atividade, p["atividade"])
        pagina = L.montar(atividade, atividade.linhas_por_resposta)[0]
    imagem = _como_aplicativo(desenhar(pagina, p["codigos"][0], {p["o1"]: "B"}, com_marcas=False))
    cliente_web.post(f"/atividades/{p['atividade']}/digitalizacoes",
                     files=[("arquivos", ("app.png", cv2.imencode(".png", imagem)[1].tobytes(), "image/png"))])
    r = cliente_web.post(f"{_url(p)}/ler")
    assert "Leitura concluída." in r.text and f'name="q{p["o1"]}" value="B" checked' in r.text
    with fabrica_sessao() as s:
        alinhamento = json.loads(s.query(LeituraPagina).one().resultado_json)["alinhamento"]
    assert alinhamento["metodo"] == "elementos" and alinhamento["caixas"] == 1 and alinhamento["erro_mm"] < 1.0



def test_ordem_pela_pauta_e_nao_pela_ordem_do_servico():
    """O serviço devolve blocos fora de ordem; a pauta da caixa decide a ordem, e as linhas viram texto corrido."""
    caixa = _layout(0, 1)[0].caixas[0]
    y1, y2, y3 = (caixa.y + k * 8 - 3 for k in (1, 2, 3))  # palavras escritas sobre a 1ª, a 2ª e a 3ª linha
    texto = {"pages": [{"blocks": [
        {"paragraphs": [{"words": [_palavra("terceira", caixa.x + 10, y3), _palavra("linha.", caixa.x + 35, y3)]}]},
        {"paragraphs": [{"words": [_palavra("linha", caixa.x + 40, y2)]}]},
        {"paragraphs": [{"words": [_palavra("linha", caixa.x + 30, y1), _palavra("Primeira", caixa.x + 8, y1),
                                   _palavra(",", caixa.x + 44, y1), _palavra("com", caixa.x + 50, y1),
                                   _palavra("divi", caixa.x + 70, y1, "HYPHEN")]}]},
        {"paragraphs": [{"words": [_palavra("são", caixa.x + 8, y2), _palavra("da", caixa.x + 25, y2)]}]},
    ]}]}
    assert ocr.textos_por_caixa(texto, [caixa]) == {
        f"q{caixa.questao_id}": "Primeira linha, com divisão da linha terceira linha."}


def test_pagina_ampliada_para_a_escrita():
    pagina = _layout(0, 1)[0]
    alinhada = alinhar(digitalizar(desenhar(pagina, "ABCD-EFGH"), angulo=1.0, semente=3), pagina)
    grande = alinhada.ampliada(ocr.ESCALA_OCR)
    assert alinhada.imagem.shape == (round(297 * ESCALA), round(210 * ESCALA))
    assert grande.shape == (round(297 * ocr.ESCALA_OCR), round(210 * ocr.ESCALA_OCR))
    # a caixa fica no mesmo lugar, em milímetros, nas duas resoluções
    c = pagina.caixas[0]
    pequena = alinhada.imagem[round((c.y - 1) * ESCALA):round((c.y + 1) * ESCALA), round(c.x * ESCALA):round((c.x + c.largura) * ESCALA)]
    ampliada = grande[round((c.y - 1) * 12):round((c.y + 1) * 12), round(c.x * 12):round((c.x + c.largura) * 12)]
    assert pequena.min() < 100 and ampliada.min() < 100  # a borda de cima da caixa aparece nas duas
