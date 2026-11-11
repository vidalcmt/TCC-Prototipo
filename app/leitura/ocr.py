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
from app.folhas.layout import LINHA_RESPOSTA
from app.leitura.alinhamento import ESCALA

ENDERECO = "https://vision.googleapis.com/v1/images:annotate"
SERVICO = "google-cloud-vision"
MARGEM_CAIXA = 2.5  # mm: a letra costuma passar um pouco da borda da caixa
# Resolução da página enviada ao serviço: cerca de 300 dpi, o padrão de digitalização para texto.
ESCALA_OCR = 12.0



class OcrIndisponivel(Exception):
    """Sem chave configurada: a leitura da escrita fica desligada."""


class OcrFalhou(Exception):
    pass


def disponivel() -> bool:
    """Se a escrita pode ser lida com o serviço escolhido em LEITURA_SERVICO."""
    if config.leitura_servico == "documentai":
        from app.leitura import documentai
        return documentai.disponivel()
    return bool(config.google_vision_api_key)


def nome_do_servico() -> str:
    return "Google Document AI" if config.leitura_servico == "documentai" else "Google Cloud Vision"


def transcrever(imagem: np.ndarray, escala: float, caixas: list, http: httpx.Client | None = None,
                servico: str | None = None) -> tuple[dict[str, str], float, str]:
    """Lê a escrita da página alinhada com o serviço escolhido.

    Devolve o texto de cada caixa, a latência em milissegundos e o nome do
    serviço. Os dois serviços entregam palavras com posição; daí em diante, a
    montagem pela pauta é a mesma.
    """
    servico = servico or config.leitura_servico
    if servico == "documentai":
        from app.leitura import documentai
        lista, latencia = documentai.palavras_da_pagina(imagem, http)
        return textos_das_palavras(lista, caixas), latencia, documentai.SERVICO
    anotacao, latencia = anotar(imagem, http)
    return textos_por_caixa(anotacao, caixas, escala), latencia, SERVICO


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
        raise OcrFalhou(explicar_erro(resposta.status_code, mensagem))
    respostas = dados.get("responses") or [{}]
    if "error" in respostas[0]:
        raise OcrFalhou(f"O Google Cloud Vision não leu a imagem: {respostas[0]['error'].get('message', '')}")
    return respostas[0].get("fullTextAnnotation") or {}, latencia


# Erros comuns na configuração, com o que fazer. A mensagem original do Google
# vem junto, para o caso de nenhuma explicação servir.
EXPLICACOES = [
    ("API key not valid", "a chave está errada ou foi apagada. Confira o valor de GOOGLE_VISION_API_KEY no .env."),
    ("SERVICE_DISABLED", "a Cloud Vision API não está ativada no projeto, ou a chave não tem permissão para ela. "
                         "Ative a API e confira as restrições da chave (guia de publicação, seção 6)."),
    ("has not been used in project", "a Cloud Vision API não está ativada no projeto. Ative a API e espere alguns "
                                     "minutos (guia de publicação, seção 6)."),
    ("are blocked", "a chave não tem permissão para a Cloud Vision API. Em Restrições da API, marque Cloud Vision API."),
    ("IP address", "a chave está restrita a outro endereço IP. Em Restrições do aplicativo, informe o IP fixo do "
                   "servidor, ou use uma chave própria para testar no computador."),
    ("billing", "o faturamento do projeto não está ativo. Vincule uma conta de faturamento ao projeto."),
]


def explicar_erro(status: int, mensagem: str) -> str:
    for trecho, explicacao in EXPLICACOES:
        if trecho.lower() in (mensagem or "").lower():
            return f"O Google Cloud Vision recusou o pedido: {explicacao} (HTTP {status}: {mensagem})"
    return f"O Google Cloud Vision recusou o pedido (HTTP {status}): {mensagem}".strip()


def palavras(anotacao: dict, escala: float = ESCALA) -> list[tuple[str, str, float, float]]:
    """Palavras com a quebra que o serviço detectou depois delas e o centro, em milímetros."""
    saida = []
    for pagina in anotacao.get("pages", []):
        for bloco in pagina.get("blocks", []):
            for paragrafo in bloco.get("paragraphs", []):
                for palavra in paragrafo.get("words", []):
                    simbolos = palavra.get("symbols", [])
                    texto = "".join(s.get("text", "") for s in simbolos)
                    vertices = (palavra.get("boundingBox") or {}).get("vertices", [])
                    if not texto or not vertices:
                        continue
                    quebra = ((simbolos[-1].get("property") or {}).get("detectedBreak") or {}).get("type", "")
                    cx = sum(v.get("x", 0) for v in vertices) / len(vertices) / escala
                    cy = sum(v.get("y", 0) for v in vertices) / len(vertices) / escala
                    saida.append((texto, quebra, cx, cy))
    return saida


def campo_da_caixa(caixa) -> str:
    """O mesmo nome do campo no formulário da folha."""
    return f"q{caixa.questao_id}" if caixa.item is None else f"q{caixa.questao_id}_{caixa.item}"


PONTUACAO_COLADA_ANTES = set(".,;:!?)]}%")
PONTUACAO_COLADA_DEPOIS = set("([{")


def textos_por_caixa(anotacao: dict, caixas: list, escala: float = ESCALA) -> dict[str, str]:
    """O texto de cada caixa a partir da resposta do Google Cloud Vision."""
    return textos_das_palavras(palavras(anotacao, escala), caixas)


def textos_das_palavras(lista: list[tuple[str, str, float, float]], caixas: list) -> dict[str, str]:
    """O texto de cada caixa, montado linha por linha pela pauta impressa.

    O serviço agrupa as palavras em blocos e parágrafos pela aparência, e com
    letra à mão esse agrupamento costuma sair errado: um pedaço da terceira
    linha vem antes da primeira, ou uma coluna de palavras vira um parágrafo.
    Por isso a ordem do serviço é descartada. A caixa tem linhas a cada 8 mm,
    em posição conhecida; cada palavra vai para a linha da pauta em que está o
    seu centro, e as palavras de uma linha são lidas da esquerda para a direita.
    """
    por_caixa: dict[str, list] = {campo_da_caixa(c): [] for c in caixas}
    for texto, quebra, x, y in lista:
        for c in caixas:
            if (c.x - MARGEM_CAIXA <= x <= c.x + c.largura + MARGEM_CAIXA
                    and c.y - MARGEM_CAIXA <= y <= c.y + c.altura + MARGEM_CAIXA):
                linha = min(max(int((y - c.y) // LINHA_RESPOSTA), 0), c.linhas - 1)
                por_caixa[campo_da_caixa(c)].append((linha, x, texto, quebra))
                break
    return {campo: _montar(itens) for campo, itens in por_caixa.items()}


def _montar(itens: list) -> str:
    """Junta as linhas da pauta num texto corrido.

    A quebra de linha na folha é só o fim do espaço da pauta, e não um novo
    parágrafo; por isso as linhas são unidas com um espaço. Uma palavra partida
    com hífen no fim da linha é reunida (\"divi-\" + \"são\" vira \"divisão\").
    """
    palavras_em_ordem = []
    for linha, _, texto, quebra in sorted(itens):
        palavras_em_ordem.append((linha, texto, quebra))
    texto_final, linha_anterior, partida = "", None, False
    for linha, texto, quebra in palavras_em_ordem:
        mudou_de_linha = linha_anterior is not None and linha != linha_anterior
        if partida and mudou_de_linha:
            texto_final = texto_final.rstrip("-") + texto  # continuação da palavra partida
        else:
            colar = (not texto_final or texto[0] in PONTUACAO_COLADA_ANTES
                     or texto_final[-1] in PONTUACAO_COLADA_DEPOIS)
            texto_final += ("" if colar else " ") + texto
        partida = quebra == "HYPHEN" or texto.endswith("-")
        linha_anterior = linha
    return texto_final
