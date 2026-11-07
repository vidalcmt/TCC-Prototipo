"""Endireita a página digitalizada usando as quatro marcas pretas dos cantos.

Depois do alinhamento, cada milímetro da folha corresponde a ESCALA pixels,
na mesma posição calculada por app/folhas/layout.py. Assim, a bolinha da
questão 3, alternativa B, está sempre no mesmo pixel, qualquer que tenha sido
a inclinação, a escala ou o deslocamento da digitalização ou da foto.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from app.folhas import layout as L

ESCALA = 8.0  # pixels por milímetro na imagem alinhada (cerca de 200 dpi)
LARGURA_PX, ALTURA_PX = round(L.LARGURA * ESCALA), round(L.ALTURA * ESCALA)


class AlinhamentoFalhou(ValueError):
    pass


@dataclass
class PaginaAlinhada:
    imagem: np.ndarray        # tons de cinza, LARGURA_PX x ALTURA_PX
    girada: bool              # a página estava de cabeça para baixo


def centros_esperados_mm() -> np.ndarray:
    return np.array([(x + L.MARCA / 2, y + L.MARCA / 2) for x, y in L.MARCAS], dtype=np.float32)


def _de_cabeca_para_baixo(imagem: np.ndarray) -> bool:
    """O QR code fica no alto da página; se ele aparece embaixo, a página está invertida."""
    try:
        ok, pontos = cv2.QRCodeDetector().detect(imagem)
    except cv2.error:
        return False
    if not ok or pontos is None:
        return False
    return float(pontos.reshape(-1, 2)[:, 1].mean()) > imagem.shape[0] / 2


def _candidatas(imagem: np.ndarray) -> list[tuple[float, float, float]]:
    """Quadrados pretos cheios: centro (x, y) e lado aproximado, em pixels."""
    altura, largura = imagem.shape[:2]
    lado_esperado = L.MARCA * largura / L.LARGURA  # supõe a folha ocupando quase toda a largura
    suave = cv2.GaussianBlur(imagem, (5, 5), 0)
    _, binaria = cv2.threshold(suave, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contornos, hierarquia = cv2.findContours(binaria, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarquia is None:
        return []
    candidatas = []
    for contorno, (_, _, filho, pai) in zip(contornos, hierarquia[0]):
        # A marca é um quadrado maciço, sem nada por dentro. Os cantos do QR code
        # também são quadrados escuros, mas vazados: têm um contorno interno.
        if filho != -1 or pai != -1:
            continue
        x, y, w, h = cv2.boundingRect(contorno)
        lado = (w + h) / 2
        if not 0.55 * lado_esperado <= lado <= 2.2 * lado_esperado:
            continue
        if not 0.7 <= w / h <= 1.4:
            continue
        area = cv2.contourArea(contorno)
        if area < 0.75 * w * h:  # quadrado cheio, não um contorno de bolinha ou de caixa
            continue
        momentos = cv2.moments(contorno)
        if momentos["m00"] == 0:
            continue
        candidatas.append((momentos["m10"] / momentos["m00"], momentos["m01"] / momentos["m00"], lado))
    return candidatas


def _quatro_marcas(imagem: np.ndarray) -> np.ndarray:
    altura, largura = imagem.shape[:2]
    candidatas = _candidatas(imagem)
    cantos = [(0, 0), (largura, 0), (0, altura), (largura, altura)]
    escolhidas = []
    for cx, cy in cantos:
        # só candidatas no quadrante do canto, a mais próxima dele
        no_quadrante = [c for c in candidatas
                        if (c[0] < largura / 2) == (cx == 0) and (c[1] < altura / 2) == (cy == 0)]
        if not no_quadrante:
            raise AlinhamentoFalhou("Não encontrei as quatro marcas pretas dos cantos da folha.")
        escolhidas.append(min(no_quadrante, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)[:2])
    return np.array(escolhidas, dtype=np.float32)


def _alinhar_nesta_posicao(imagem: np.ndarray) -> np.ndarray:
    origem = _quatro_marcas(imagem)
    destino = centros_esperados_mm() * ESCALA
    # Conferência simples: as marcas precisam formar um retângulo de proporção parecida com a esperada.
    largura_lida = np.linalg.norm(origem[1] - origem[0])
    altura_lida = np.linalg.norm(origem[2] - origem[0])
    proporcao_esperada = (destino[2][1] - destino[0][1]) / (destino[1][0] - destino[0][0])
    if largura_lida == 0 or abs(altura_lida / largura_lida - proporcao_esperada) > 0.15 * proporcao_esperada:
        raise AlinhamentoFalhou("As marcas encontradas não formam o retângulo esperado da folha.")
    matriz = cv2.getPerspectiveTransform(origem, destino)
    return cv2.warpPerspective(imagem, matriz, (LARGURA_PX, ALTURA_PX), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=255)


def _tinta_no_qr(alinhada: np.ndarray) -> float:
    """Fração escura na posição do QR code: cerca de metade numa página na posição certa."""
    regiao = recorte(alinhada, L.QR_X, L.QR_Y, L.QR_LADO, L.QR_LADO, margem=0)
    return float((regiao < np.percentile(alinhada, 90) * 0.6).mean())


def alinhar(imagem: np.ndarray) -> PaginaAlinhada:
    """Alinha a página e confere a orientação pela posição do QR code.

    As quatro marcas são iguais, então elas sozinhas não dizem se a página está
    de cabeça para baixo. O QR code diz: primeiro pela detecção do OpenCV e,
    se ela falhar, pela quantidade de tinta onde o QR code deveria estar.
    """
    girada = _de_cabeca_para_baixo(imagem)
    primeira = cv2.rotate(imagem, cv2.ROTATE_180) if girada else imagem
    alinhada = _alinhar_nesta_posicao(primeira)
    if _tinta_no_qr(alinhada) < 0.25:
        try:
            outra = _alinhar_nesta_posicao(cv2.rotate(primeira, cv2.ROTATE_180))
        except AlinhamentoFalhou:
            outra = None
        if outra is not None and _tinta_no_qr(outra) > _tinta_no_qr(alinhada):
            alinhada, girada = outra, not girada
    return PaginaAlinhada(imagem=alinhada, girada=girada)


def recorte(alinhada: np.ndarray, x: float, y: float, largura: float, altura: float, margem: float = 2.0) -> np.ndarray:
    """Região da página alinhada, em milímetros."""
    x0, y0 = max(0, round((x - margem) * ESCALA)), max(0, round((y - margem) * ESCALA))
    x1 = min(LARGURA_PX, round((x + largura + margem) * ESCALA))
    y1 = min(ALTURA_PX, round((y + altura + margem) * ESCALA))
    return alinhada[y0:y1, x0:x1]
