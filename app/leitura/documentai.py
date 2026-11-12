"""Leitura da escrita com o Google Document AI (processador Enterprise Document OCR).

Alternativa ao Google Cloud Vision, escolhida com LEITURA_SERVICO=documentai.
O Document AI usa um modelo de OCR mais recente, com detecção de letra à mão
ligada por padrão e melhorias na ordem de leitura. O preço por página é o
mesmo do Vision, com as primeiras 1.000 páginas gratuitas.

A autenticação não usa chave de API: usa a conta de serviço da máquina no
Google Cloud (no servidor) ou o login do gcloud (no computador), pela
biblioteca google-auth. O guia de publicação, seção 6.5, explica a
configuração.

A resposta traz cada palavra (token) com a posição normalizada na imagem,
de 0 a 1. Como a imagem enviada é a página alinhada inteira, a posição vira
milímetros multiplicando pela largura e pela altura da folha, e a montagem do
texto pela pauta das caixas é a mesma do Vision (ocr.textos_das_palavras).
"""

import base64
import time

import cv2
import httpx
import numpy as np

from app.config import config
from app.folhas import layout as L
from app.leitura.ocr import OcrFalhou, OcrIndisponivel

SERVICO = "google-document-ai"
ESCOPO = "https://www.googleapis.com/auth/cloud-platform"

_credenciais = None


def disponivel() -> bool:
    return bool(config.documentai_processador.strip())


def _endereco() -> str:
    processador = config.documentai_processador.strip().strip("/")
    partes = processador.split("/")
    if len(partes) < 6 or partes[0] != "projects" or partes[2] != "locations" or partes[4] != "processors":
        raise OcrIndisponivel("DOCUMENTAI_PROCESSADOR deve ter o formato "
                              "projects/PROJETO/locations/us/processors/ID.")
    return f"https://{partes[3]}-documentai.googleapis.com/v1/{processador}:process"


def _token() -> str:
    """Token de acesso da conta de serviço da máquina, renovado quando vence."""
    global _credenciais
    try:
        import google.auth
        import google.auth.transport.requests
    except ImportError:
        raise OcrIndisponivel("Falta a biblioteca google-auth: rode pip install -r requirements.txt.")
    try:
        if _credenciais is None:
            _credenciais, _ = google.auth.default(scopes=[ESCOPO])
        if not _credenciais.valid:
            _credenciais.refresh(google.auth.transport.requests.Request())
    except Exception as erro:
        raise OcrFalhou("Não foi possível obter as credenciais do Google para o Document AI. No servidor, a "
                        "máquina precisa do acesso \"cloud-platform\"; no computador, rode "
                        f"gcloud auth application-default login (guia de publicação, seção 6.5). ({erro})")
    return _credenciais.token


EXPLICACOES = [
    ("PERMISSION_DENIED", "a conta de serviço da máquina não tem permissão para usar o Document AI. Dê a ela o "
                          "papel \"Usuário da API Document AI\" (guia de publicação, seção 6.5)."),
    ("has not been used in project", "a Document AI API não está ativada no projeto."),
    ("SERVICE_DISABLED", "a Document AI API não está ativada no projeto."),
    ("NOT_FOUND", "o processador não foi encontrado. Confira DOCUMENTAI_PROCESSADOR no .env."),
    ("ACCESS_TOKEN_SCOPE_INSUFFICIENT", "a máquina não tem o acesso \"cloud-platform\". Pare a máquina, edite os "
                                        "escopos de acesso e permita acesso completo às APIs do Cloud."),
    ("billing", "o faturamento do projeto não está ativo."),
]


def _explicar(status: int, mensagem: str) -> str:
    for trecho, explicacao in EXPLICACOES:
        if trecho.lower() in (mensagem or "").lower():
            return f"O Document AI recusou o pedido: {explicacao} (HTTP {status}: {mensagem})"
    return f"O Document AI recusou o pedido (HTTP {status}): {mensagem}".strip()


def processar(imagem: np.ndarray, http: httpx.Client | None = None) -> tuple[dict, float]:
    """Envia a página e devolve o documento lido e a latência em milissegundos."""
    if not disponivel():
        raise OcrIndisponivel("Configure DOCUMENTAI_PROCESSADOR no .env para ler a escrita com o Document AI.")
    endereco = _endereco()
    ok, jpeg = cv2.imencode(".jpg", imagem, [cv2.IMWRITE_JPEG_QUALITY, 90])
    corpo = {
        "rawDocument": {"content": base64.b64encode(jpeg.tobytes()).decode(), "mimeType": "image/jpeg"},
        "processOptions": {"ocrConfig": {"hints": {"languageHints": ["pt"]}}},
    }
    cabecalhos = {"Authorization": f"Bearer {_token()}"}
    cliente = http or httpx.Client(timeout=90)
    inicio = time.perf_counter()
    try:
        resposta = cliente.post(endereco, json=corpo, headers=cabecalhos)
    except httpx.HTTPError as erro:
        raise OcrFalhou(f"Falha de rede ao chamar o Document AI: {erro.__class__.__name__}")
    finally:
        if http is None:
            cliente.close()
    latencia = (time.perf_counter() - inicio) * 1000
    try:
        dados = resposta.json()
    except ValueError:
        raise OcrFalhou(f"Resposta inválida do Document AI (HTTP {resposta.status_code}).")
    if resposta.status_code != 200:
        erro = dados.get("error") or {} if isinstance(dados, dict) else {}
        mensagem = f"{erro.get('status', '')} {erro.get('message', '')}".strip()
        raise OcrFalhou(_explicar(resposta.status_code, mensagem))
    return dados.get("document") or {}, latencia


def _texto_do_trecho(documento: dict, layout: dict) -> str:
    texto = documento.get("text", "")
    partes = []
    for segmento in (layout.get("textAnchor") or {}).get("textSegments", []):
        inicio, fim = int(segmento.get("startIndex", 0)), int(segmento.get("endIndex", 0))
        partes.append(texto[inicio:fim])
    return "".join(partes).strip()


SOBREPOSICAO_MAXIMA = 0.5  # fração da área da menor palavra


def _sobreposicao(a: tuple, b: tuple) -> float:
    """Quanto dois retângulos (x0, y0, x1, y1) se cobrem, como fração da área do menor."""
    largura = min(a[2], b[2]) - max(a[0], b[0])
    altura = min(a[3], b[3]) - max(a[1], b[1])
    if largura <= 0 or altura <= 0:
        return 0.0
    menor = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return largura * altura / menor if menor > 0 else 0.0


def palavras(documento: dict) -> list[tuple[str, str, float, float]]:
    """Palavras com a quebra detectada depois delas e o centro, em milímetros da folha.

    Em letra à mão, o Document AI às vezes devolve a mesma palavra duas vezes,
    em dois tokens quase no mesmo lugar, e o texto saía com "o o meio meio".
    Duas palavras escritas pelo aluno não ocupam o mesmo espaço no papel: quando
    um token cobre mais da metade de outro, fica só o de maior confiança.
    """
    candidatos = []
    for pagina in documento.get("pages", []):
        for token in pagina.get("tokens", []):
            layout = token.get("layout") or {}
            texto = _texto_do_trecho(documento, layout)
            vertices = (layout.get("boundingPoly") or {}).get("normalizedVertices", [])
            if not texto or not vertices:
                continue
            xs, ys = [v.get("x", 0) for v in vertices], [v.get("y", 0) for v in vertices]
            caixa = (min(xs), min(ys), max(xs), max(ys))
            confianca = float(layout.get("confidence", 0) or 0)
            quebra = (token.get("detectedBreak") or {}).get("type", "")
            candidatos.append((texto, quebra, sum(xs) / len(xs) * L.LARGURA, sum(ys) / len(ys) * L.ALTURA,
                               caixa, confianca))
    mantidos = []
    for candidato in sorted(candidatos, key=lambda c: -c[5]):
        if all(_sobreposicao(candidato[4], m[4]) <= SOBREPOSICAO_MAXIMA for m in mantidos):
            mantidos.append(candidato)
    ordem = {id(c): i for i, c in enumerate(candidatos)}
    return [(t, q, x, y) for t, q, x, y, _, _ in sorted(mantidos, key=lambda c: ordem[id(c)])]


def palavras_da_pagina(imagem: np.ndarray, http: httpx.Client | None = None) -> tuple[list, float]:
    documento, latencia = processar(imagem, http)
    return palavras(documento), latencia
