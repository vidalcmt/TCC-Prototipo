"""Transcrição da escrita à mão com o Google Cloud Vision (reconhecimento de texto).

A página alinhada inteira é enviada numa única chamada, com o recurso
DOCUMENT_TEXT_DETECTION, indicado para texto denso e manuscrito. A resposta
traz cada palavra com a sua posição na imagem; como a imagem está alinhada,
a posição em pixels vira posição em milímetros, e cada palavra é atribuída
à caixa de resposta em que está. O texto impresso (cabeçalho, rótulos) fica
fora das caixas e é descartado.

A transcrição é literal: nenhum ajuste de ortografia ou de sentido é feito,
porque a correção precisa avaliar o que o aluno escreveu. O professor confere
o texto antes de ele ser corrigido.
"""

import base64
import time

import cv2
import httpx
import numpy as np

from app.config import config
from app.leitura.alinhamento import ESCALA

ENDERECO = "https://vision.googleapis.com/v1/images:annotate"
SERVICO = "google-cloud-vision"
MARGEM_CAIXA = 2.5  # mm: a letra costuma passar um pouco da borda da caixa

QUEBRAS = {"SPACE": " ", "SURE_SPACE": " ", "EOL_SURE_SPACE": "\n", "LINE_BREAK": "\n", "HYPHEN": "-\n"}


class OcrIndisponivel(Exception):
    """Sem chave configurada: a leitura da escrita fica desligada."""


class OcrFalhou(Exception):
    pass


def disponivel() -> bool:
    return bool(config.google_vision_api_key)


def anotar(imagem: np.ndarray, http: httpx.Client | None = None) -> tuple[dict, float]:
    """Envia a imagem e devolve a anotação completa do texto e a latência em milissegundos."""
    if not disponivel():
        raise OcrIndisponivel("Configure GOOGLE_VISION_API_KEY no .env para ler a escrita.")
    ok, jpeg = cv2.imencode(".jpg", imagem, [cv2.IMWRITE_JPEG_QUALITY, 90])
    corpo = {"requests": [{
        "image": {"content": base64.b64encode(jpeg.tobytes()).decode()},
        "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
        "imageContext": {"languageHints": ["pt"]},
    }]}
    cliente = http or httpx.Client(timeout=60)
    inicio = time.perf_counter()
    try:
        resposta = cliente.post(ENDERECO, params={"key": config.google_vision_api_key}, json=corpo)
    except httpx.HTTPError as erro:
        raise OcrFalhou(f"Falha de rede ao chamar o Google Cloud Vision: {erro.__class__.__name__}")
    finally:
        if http is None:
            cliente.close()
    latencia = (time.perf_counter() - inicio) * 1000
    try:
        dados = resposta.json()
    except ValueError:
        raise OcrFalhou(f"Resposta inválida do Google Cloud Vision (HTTP {resposta.status_code}).")
    if resposta.status_code != 200 or "error" in dados:
        mensagem = (dados.get("error") or {}).get("message", "") if isinstance(dados, dict) else ""
        raise OcrFalhou(f"O Google Cloud Vision recusou o pedido (HTTP {resposta.status_code}): {mensagem}".strip())
    respostas = dados.get("responses") or [{}]
    if "error" in respostas[0]:
        raise OcrFalhou(f"O Google Cloud Vision não leu a imagem: {respostas[0]['error'].get('message', '')}")
    return respostas[0].get("fullTextAnnotation") or {}, latencia


def palavras(anotacao: dict) -> list[tuple[str, float, float]]:
    """Palavras em ordem de leitura, com a quebra que vem depois e o centro em milímetros."""
    saida = []
    for pagina in anotacao.get("pages", []):
        for bloco in pagina.get("blocks", []):
            for paragrafo in bloco.get("paragraphs", []):
                for palavra in paragrafo.get("words", []):
                    simbolos = palavra.get("symbols", [])
                    texto = "".join(s.get("text", "") for s in simbolos)
                    if not texto:
                        continue
                    quebra = ((simbolos[-1].get("property") or {}).get("detectedBreak") or {}).get("type", "")
                    vertices = (palavra.get("boundingBox") or {}).get("vertices", [])
                    if not vertices:
                        continue
                    cx = sum(v.get("x", 0) for v in vertices) / len(vertices) / ESCALA
                    cy = sum(v.get("y", 0) for v in vertices) / len(vertices) / ESCALA
                    saida.append((texto + QUEBRAS.get(quebra, ""), cx, cy))
    return saida


def campo_da_caixa(caixa) -> str:
    """O mesmo nome do campo no formulário da folha."""
    return f"q{caixa.questao_id}" if caixa.item is None else f"q{caixa.questao_id}_{caixa.item}"


def textos_por_caixa(anotacao: dict, caixas: list) -> dict[str, str]:
    textos = {campo_da_caixa(c): "" for c in caixas}
    for texto, x, y in palavras(anotacao):
        for c in caixas:
            if (c.x - MARGEM_CAIXA <= x <= c.x + c.largura + MARGEM_CAIXA
                    and c.y - MARGEM_CAIXA <= y <= c.y + c.altura + MARGEM_CAIXA):
                textos[campo_da_caixa(c)] += texto
                break
    return {campo: _limpar(t) for campo, t in textos.items()}


def _limpar(texto: str) -> str:
    """Um espaço entre as palavras e uma linha por linha escrita, sem linhas vazias."""
    linhas = (" ".join(linha.split()) for linha in texto.split("\n"))
    return "\n".join(linha for linha in linhas if linha)
