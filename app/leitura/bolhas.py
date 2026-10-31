"""Leitura das bolinhas das objetivas na página alinhada (OMR).

Para cada bolinha, mede-se a fração de pixels escuros num disco um pouco menor
que o círculo impresso, para não contar o contorno. A letra impressa dentro
da bolinha escurece uma pequena parte do disco; uma bolinha preenchida a
caneta escurece a maior parte. Valores intermediários, como um X ou um
preenchimento fraco, são marcados como duvidosos para o professor conferir.
"""

from dataclasses import dataclass, field

import numpy as np

from app.leitura.alinhamento import ESCALA

MARCADA = 0.40     # a partir daqui, a bolinha está preenchida
DUVIDA = 0.20      # entre DUVIDA e MARCADA, pode ser uma marca incompleta
RAIO_UTIL = 0.72   # fração do raio medida (o contorno impresso fica de fora)


@dataclass
class LeituraObjetiva:
    marcada: str            # letra, "branco" ou "multipla" (os mesmos valores do formulário)
    duvida: bool
    preenchimento: dict[str, float] = field(default_factory=dict)


def nivel_do_papel(imagem: np.ndarray) -> float:
    return float(np.percentile(imagem, 90))


def preenchimento(imagem: np.ndarray, x_mm: float, y_mm: float, r_mm: float, limiar: float) -> float:
    cx, cy, r = x_mm * ESCALA, y_mm * ESCALA, r_mm * RAIO_UTIL * ESCALA
    x0, x1 = int(cx - r), int(cx + r) + 1
    y0, y1 = int(cy - r), int(cy + r) + 1
    janela = imagem[y0:y1, x0:x1].astype(np.float32)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    disco = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    if not disco.any():
        return 0.0
    return float((janela[disco] < limiar).mean())


def ler_questao(imagem: np.ndarray, bolhas: list, limiar: float) -> LeituraObjetiva:
    valores = {b.letra: round(preenchimento(imagem, b.x, b.y, b.r, limiar), 3) for b in bolhas}
    marcadas = [letra for letra, v in valores.items() if v >= MARCADA]
    duvidosas = [letra for letra, v in valores.items() if DUVIDA <= v < MARCADA]
    if len(marcadas) > 1:
        return LeituraObjetiva("multipla", bool(duvidosas), valores)
    if len(marcadas) == 1:
        return LeituraObjetiva(marcadas[0], bool(duvidosas), valores)
    if duvidosas:
        return LeituraObjetiva(max(duvidosas, key=valores.get), True, valores)
    return LeituraObjetiva("branco", False, valores)


def ler_bolhas(imagem: np.ndarray, pagina) -> dict[int, LeituraObjetiva]:
    """Uma leitura por questão objetiva da página do layout, pelo id da questão."""
    limiar = nivel_do_papel(imagem) * 0.6
    por_questao: dict[int, list] = {}
    for bolha in pagina.bolhas:
        por_questao.setdefault(bolha.questao_id, []).append(bolha)
    return {qid: ler_questao(imagem, bolhas, limiar) for qid, bolhas in por_questao.items()}
