"""Envio das folhas digitalizadas e identificação pelo QR code."""

import cv2
import numpy as np
import pymupdf
import pytest
import qrcode

from app.config import config
from app.digitalizacao.servico import ler_qr_da_imagem
from app.folhas import layout as L
from app.models import Atividade, PaginaDigitalizada
from tests.test_resultados import _url, prova  # noqa: F401

DPI = 200
MM = DPI / 25.4


@pytest.fixture(autouse=True)
def pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "pasta_arquivos", tmp_path)
    return tmp_path


def folha_sintetica(texto_qr: str | None, girar=False, ruido=False) -> np.ndarray:
    """Uma página A4 branca, a 200 dpi, com as marcas dos cantos e o QR code nas posições do layout."""
    img = np.full((round(297 * MM), round(210 * MM)), 255, np.uint8)
    for x, y in L.MARCAS:
        img[round(y * MM):round((y + L.MARCA) * MM), round(x * MM):round((x + L.MARCA) * MM)] = 0
    if texto_qr:
        matriz = _matriz(texto_qr)
        lado = round(L.QR_LADO * MM)
        modulo = cv2.resize((~matriz * 255).astype(np.uint8), (lado, lado), interpolation=cv2.INTER_NEAREST)
        y0, x0 = round(L.QR_Y * MM), round(L.QR_X * MM)
        img[y0:y0 + lado, x0:x0 + lado] = modulo
    if ruido:
        img = cv2.GaussianBlur(img, (3, 3), 0)
        img = np.clip(img.astype(int) + np.random.default_rng(1).integers(-25, 25, img.shape), 0, 255).astype(np.uint8)
    if girar:
        img = cv2.rotate(img, cv2.ROTATE_180)
    return img


def _matriz(texto):
    qr = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(texto)
    qr.make(fit=True)
    return np.array(qr.get_matrix(), dtype=bool)


def _pdf(*imagens) -> bytes:
    documento = pymupdf.open()
    for img in imagens:
        pagina = documento.new_page(width=595, height=842)
        pagina.insert_image(pagina.rect, stream=cv2.imencode(".png", img)[1].tobytes())
    return documento.tobytes()


def _png(img) -> bytes:
    return cv2.imencode(".png", img)[1].tobytes()


def _enviar(cliente, p, *arquivos):
    return cliente.post(f"/atividades/{p['atividade']}/digitalizacoes",
                        files=[("arquivos", (nome, conteudo, "application/octet-stream")) for nome, conteudo in arquivos])


# ---------- leitura do QR ----------

@pytest.mark.parametrize("girar, ruido", [(False, False), (True, False), (False, True)])
def test_qr_lido_em_pagina_reta_girada_e_com_ruido(girar, ruido):
    img = folha_sintetica(L.conteudo_qr("ABCD-EFGH", 2), girar=girar, ruido=ruido)
    assert ler_qr_da_imagem(img) == ("ABCD-EFGH", 2)


def test_pagina_sem_qr():
    assert ler_qr_da_imagem(folha_sintetica(None)) is None


# ---------- envio ----------

def test_pdf_com_varias_folhas_e_foto_sem_qr(fabrica_sessao, cliente_web, prova, pasta):
    p = prova
    pdf = _pdf(folha_sintetica(L.conteudo_qr(p["codigos"][1], 1)), folha_sintetica(L.conteudo_qr(p["codigos"][0], 1)))
    r = _enviar(cliente_web, p, ("turma.pdf", pdf), ("foto.png", _png(folha_sintetica(None))))
    assert "3 páginas recebidas; 2 identificadas pelo QR code; 1 sem QR code legível" in r.text
    with fabrica_sessao() as s:
        paginas = s.query(PaginaDigitalizada).order_by(PaginaDigitalizada.id).all()
        assert [(pg.folha_id, pg.pagina, pg.situacao) for pg in paginas] == [
            (p["folhas"][1], 1, "identificada"), (p["folhas"][0], 1, "identificada"), (None, None, "sem_qr")]
        assert [pg.pagina_do_arquivo for pg in paginas] == [1, 2, 1]
        assert all((pasta / pg.arquivo).is_file() for pg in paginas)
    # a imagem aparece ao lado das respostas da folha
    assert "Folha digitalizada" in cliente_web.get(_url(p, 1)).text


def test_pagina_de_outra_atividade_e_reenvio_substitui(fabrica_sessao, cliente_web, prova):
    p = prova
    _enviar(cliente_web, p, ("a.png", _png(folha_sintetica(L.conteudo_qr(p["codigos"][0], 1)))))
    r = _enviar(cliente_web, p, ("b.png", _png(folha_sintetica(L.conteudo_qr(p["codigos"][0], 1)))),
                ("c.png", _png(folha_sintetica(L.conteudo_qr("ZZZZ-ZZZZ", 1)))))
    assert "1 de outra atividade" in r.text and "1 substituíram páginas enviadas antes" in r.text
    with fabrica_sessao() as s:
        assert [pg.situacao for pg in s.query(PaginaDigitalizada).order_by(PaginaDigitalizada.id)] == [
            "substituida", "identificada", "outra_atividade"]


def test_arquivo_recusado(fabrica_sessao, cliente_web, prova):
    r = _enviar(cliente_web, prova, ("notas.txt", b"oi"), ("quebrado.pdf", b"nao e pdf"))
    assert "notas.txt: envie PDF, PNG ou JPG" in r.text and "quebrado.pdf: o PDF não pôde ser aberto" in r.text
    with fabrica_sessao() as s:
        assert s.query(PaginaDigitalizada).count() == 0


def test_atividade_sem_folhas_nao_recebe(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        a = Atividade(titulo="Vazia")
        s.add(a)
        s.commit()
        aid = a.id
    r = _enviar(cliente_web, {"atividade": aid}, ("a.png", _png(folha_sintetica(None))))
    assert "Gere as folhas de resposta" in r.text


# ---------- conferência ----------

def test_indicar_folha_manual_e_excluir(fabrica_sessao, cliente_web, prova, pasta):
    p = prova
    _enviar(cliente_web, p, ("foto.png", _png(folha_sintetica(None))), ("foto2.png", _png(folha_sintetica(None))))
    with fabrica_sessao() as s:
        primeira, segunda = (pg.id for pg in s.query(PaginaDigitalizada).order_by(PaginaDigitalizada.id))
    base = f"/atividades/{p['atividade']}/digitalizacoes"
    assert "Nenhuma folha desta atividade tem o código" in cliente_web.post(
        f"{base}/{primeira}/atribuir", data={"codigo": "AAAA-AAAA", "pagina": "1"}).text
    assert "A folha tem 1 página." in cliente_web.post(
        f"{base}/{primeira}/atribuir", data={"codigo": p["codigos"][2], "pagina": "2"}).text
    r = cliente_web.post(f"{base}/{primeira}/atribuir", data={"codigo": p["codigos"][2].lower(), "pagina": "1"})
    assert "Página ligada à folha." in r.text
    with fabrica_sessao() as s:
        pg = s.get(PaginaDigitalizada, primeira)
        assert (pg.folha_id, pg.pagina, pg.situacao) == (p["folhas"][2], 1, "identificada")
        arquivo = pasta / s.get(PaginaDigitalizada, segunda).arquivo
    cliente_web.post(f"{base}/{segunda}/excluir")
    with fabrica_sessao() as s:
        assert s.get(PaginaDigitalizada, segunda) is None
    assert not arquivo.exists()


def test_imagem_servida_so_com_login_e_na_atividade_certa(fabrica_sessao, cliente_web, cliente_anonimo, prova):
    p = prova
    _enviar(cliente_web, p, ("a.png", _png(folha_sintetica(L.conteudo_qr(p["codigos"][0], 1)))))
    with fabrica_sessao() as s:
        pid = s.query(PaginaDigitalizada).one().id
        outra = Atividade(titulo="Outra")
        s.add(outra)
        s.commit()
        oid = outra.id
    r = cliente_web.get(f"/atividades/{p['atividade']}/digitalizacoes/{pid}/imagem")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert cliente_web.get(f"/atividades/{oid}/digitalizacoes/{pid}/imagem").status_code == 404
    cliente_web.post("/sair")
    assert cliente_anonimo.get(f"/atividades/{p['atividade']}/digitalizacoes/{pid}/imagem",
                               follow_redirects=False).status_code == 303


def test_atividade_com_digitalizacoes_nao_e_excluida_nem_descarta_folhas(fabrica_sessao, cliente_web, prova):
    p = prova
    _enviar(cliente_web, p, ("a.png", _png(folha_sintetica(None))))
    assert "não pode ser excluída" in cliente_web.post(f"/atividades/{p['atividade']}/excluir").text
    assert "não podem ser descartadas" in cliente_web.post(f"/atividades/{p['atividade']}/folhas/descartar").text
    with fabrica_sessao() as s:
        assert s.get(Atividade, p["atividade"]) is not None
