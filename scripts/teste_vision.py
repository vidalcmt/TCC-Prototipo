"""Confere se a chave do Google Cloud Vision está funcionando.

Uso (com GOOGLE_VISION_API_KEY no .env):
    python -m scripts.teste_vision

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


def main() -> int:
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


if __name__ == "__main__":
    sys.exit(main())
