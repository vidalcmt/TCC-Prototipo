"""Confere se a leitura da escrita está funcionando.

Uso:
    python -m scripts.teste_vision                # Google Cloud Vision (GOOGLE_VISION_API_KEY)
    python -m scripts.teste_vision --documentai   # Google Document AI (DOCUMENTAI_PROCESSADOR)

No servidor:
    cd /opt/devolutiva && sudo -u devolutiva .venv/bin/python -m scripts.teste_vision

Desenha uma frase numa imagem, envia ao Google Cloud Vision e mostra o que
foi lido. Gasta uma das 1.000 leituras gratuitas do mês. Não mostra a chave.
"""

import sys

import cv2
import numpy as np

from app.config import config
from app.leitura import ocr

FRASE = "Devolutiva teste 2026"


def imagem_de_teste() -> np.ndarray:
    imagem = np.full((200, 900), 255, np.uint8)
    cv2.putText(imagem, FRASE, (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 2.0, 0, 4, cv2.LINE_AA)
    return imagem


def main(argumentos: list[str] | None = None) -> int:
    argumentos = sys.argv[1:] if argumentos is None else argumentos
    if "--documentai" in argumentos:
        return testar_documentai()
    chave = config.google_vision_api_key
    if not chave:
        print("GOOGLE_VISION_API_KEY não está no .env. Veja deploy/README.md, seção 6.")
        return 1
    print(f"Chave encontrada ({len(chave)} caracteres, termina em ...{chave[-4:]}). Enviando uma imagem de teste...")
    try:
        anotacao, latencia = ocr.anotar(imagem_de_teste())
    except (ocr.OcrFalhou, ocr.OcrIndisponivel) as erro:
        print(f"Falhou. {erro}")
        return 1
    lido = " ".join((anotacao.get("text") or "").split())
    print(f"Funcionou em {latencia:.0f} ms.")
    print(f"Escrito na imagem: {FRASE}")
    print(f"Lido pelo Vision:  {lido or '(nada)'}")
    return 0


def testar_documentai() -> int:
    from app.leitura import documentai
    if not documentai.disponivel():
        print("DOCUMENTAI_PROCESSADOR não está no .env. Veja deploy/README.md, seção 6.5.")
        return 1
    print("Processador configurado. Enviando uma imagem de teste ao Document AI...")
    try:
        lista, latencia = documentai.palavras_da_pagina(imagem_de_teste())
    except (ocr.OcrFalhou, ocr.OcrIndisponivel) as erro:
        print(f"Falhou. {erro}")
        return 1
    print(f"Funcionou em {latencia:.0f} ms.")
    print(f"Escrito na imagem: {FRASE}")
    print(f"Lido pelo Document AI: {' '.join(p[0] for p in lista) or '(nada)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
