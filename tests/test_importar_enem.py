"""Testa o importador com uma API falsa, sem acessar a internet."""

import httpx

from app.models import Questao
from scripts.importar_enem import buscar_questoes, filtrar, importar_no_banco, montar_enunciado


def questao(indice, area="ciencias-humanas", arquivos=(), contexto="Texto base.", alt_arquivo=None):
    return {
        "title": f"Questão {indice} - ENEM 2023", "index": indice, "discipline": area,
        "language": None, "year": 2023, "context": contexto, "files": list(arquivos),
        "correctAlternative": "B", "alternativesIntroduction": "Assinale a correta.",
        "alternatives": [
            {"letter": l, "text": f"Alternativa {l}", "file": alt_arquivo if l == "A" else None,
             "isCorrect": l == "B"}
            for l in "ABCDE"
        ],
    }


PROVA = [
    questao(46),
    questao(47, arquivos=["https://enem.dev/img.png"]),     # imagem no enunciado
    questao(48, contexto="Veja: ![mapa](https://x/y.png)"),  # imagem no Markdown
    questao(49, alt_arquivo="https://enem.dev/alt.png"),     # imagem em alternativa
    questao(91, area="ciencias-natureza"),
]


def test_paginacao_percorre_todas_as_paginas():
    def responder(request: httpx.Request):
        offset = int(request.url.params["offset"])
        pagina = PROVA[offset:offset + 50]
        return httpx.Response(200, json={
            "metadata": {"limit": 50, "offset": offset, "total": len(PROVA), "hasMore": False},
            "questions": pagina,
        })

    cliente = httpx.Client(base_url="https://api.teste/v1", transport=httpx.MockTransport(responder))
    assert len(buscar_questoes(2023, cliente, espera=0)) == 5


def test_filtro_mantem_so_a_area_e_so_texto():
    assert [q["index"] for q in filtrar(PROVA, "ciencias-humanas")] == [46]
    assert [q["index"] for q in filtrar(PROVA, "ciencias-humanas", exigir_texto=False)] == [46, 47, 48, 49]


def test_enunciado_junta_contexto_e_introducao():
    assert montar_enunciado(PROVA[0]) == "Texto base.\n\nAssinale a correta."


def test_importacao_grava_gabarito_e_nao_duplica(sessao):
    assert importar_no_banco([PROVA[0]], sessao) == 1
    assert importar_no_banco([PROVA[0]], sessao) == 0

    q = sessao.query(Questao).one()
    assert q.tipo == "objetiva" and q.fonte == "ENEM 2023, questão 46"
    assert [a.letra for a in q.alternativas if a.correta] == ["B"]
    assert len(q.alternativas) == 5
