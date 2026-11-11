"""Endireita a página digitalizada usando as quatro marcas pretas dos cantos.

Quando as marcas não aparecem, a página é alinhada pelo QR code e pelas caixas
de resposta (app/leitura/elementos.py). O método usado e o erro medido ficam
guardados com a leitura, para comparar os dois.

Depois do alinhamento, cada milímetro da folha corresponde a ESCALA pixels,
na mesma posição calculada por app/folhas/layout.py. Assim, a bolinha da
questão 3, alternativa B, está sempre no mesmo pixel, qualquer que tenha sido
a inclinação, a escala ou o deslocamento da digitalização ou da foto.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from app.folhas import layout as L
from app.leitura import elementos

ESCALA = 8.0  # pixels por milímetro na imagem alinhada (cerca de 200 dpi)
LARGURA_PX, ALTURA_PX = round(L.LARGURA * ESCALA), round(L.ALTURA * ESCALA)


class AlinhamentoFalhou(ValueError):
    pass


MARCAS, ELEMENTOS, APROXIMADO = "marcas", "elementos", "aproximado"
ROTULOS_METODO = {
    MARCAS: "pelas marcas dos cantos",
    ELEMENTOS: "pelo QR code e pelas caixas de resposta, sem as marcas dos cantos",
    APROXIMADO: "de forma aproximada, pelas bordas da imagem, sem as marcas dos cantos",
}


@dataclass
class PaginaAlinhada:
    imagem: np.ndarray        # tons de cinza, LARGURA_PX x ALTURA_PX
    girada: bool              # a página estava de cabeça para baixo
    metodo: str = MARCAS      # "marcas", "elementos" (QR code e caixas) ou "aproximado" (bordas da imagem)
    erro_mm: float | None = None   # distância média entre as caixas esperadas e as encontradas
    caixas_usadas: int = 0
    # Para refazer o alinhamento em outra resolução: a imagem de origem (já em pé)
    # e a transformação que leva os pixels dela aos pixels da página alinhada.
    origem: np.ndarray | None = None
    matriz: np.ndarray | None = None

    def ampliada(self, escala: float) -> np.ndarray:
        """A mesma página alinhada, com `escala` pixels por milímetro.

        A transcrição da escrita usa mais resolução do que a leitura das
        bolinhas: a 8 pixels por milímetro, a letra miúda perde detalhes que a
        foto original tinha.
        """
        if self.origem is None or self.matriz is None or escala == ESCALA:
            return self.imagem
        matriz = np.diag([escala / ESCALA, escala / ESCALA, 1.0]) @ self.matriz
        tamanho = (round(L.LARGURA * escala), round(L.ALTURA * escala))
        return cv2.warpPerspective(self.origem, matriz, tamanho, flags=cv2.INTER_CUBIC,
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=255)


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


def _alinhar_nesta_posicao(imagem: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
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
                               borderMode=cv2.BORDER_CONSTANT, borderValue=255), matriz


def _tinta_no_qr(alinhada: np.ndarray) -> float:
    """Fração escura na posição do QR code: cerca de metade numa página na posição certa."""
    regiao = recorte(alinhada, L.QR_X, L.QR_Y, L.QR_LADO, L.QR_LADO, margem=0)
    return float((regiao < np.percentile(alinhada, 90) * 0.6).mean())


def alinhar(imagem: np.ndarray, pagina_layout=None) -> PaginaAlinhada:
    """Alinha pelas marcas e, sem elas, pelo QR code e pelas caixas da página do layout."""
    try:
        alinhada = alinhar_pelas_marcas(imagem)
    except AlinhamentoFalhou as erro_marcas:
        if pagina_layout is None:
            raise
        try:
            return alinhar_pelos_elementos(imagem, pagina_layout)
        except elementos.ElementosInsuficientes as erro:
            raise AlinhamentoFalhou(f"{erro_marcas} {erro}")
    if pagina_layout is not None and pagina_layout.caixas:
        alinhada.erro_mm, alinhada.caixas_usadas = erro_das_caixas(alinhada.imagem, pagina_layout)
    return alinhada


def alinhar_pelos_elementos(imagem: np.ndarray, pagina_layout) -> PaginaAlinhada:
    # As caixas são procuradas de cima para baixo: a página precisa estar em pé antes.
    girada = _de_cabeca_para_baixo(imagem)
    if girada:
        imagem = cv2.rotate(imagem, cv2.ROTATE_180)
    imagem = _endireitar(imagem)
    matriz, erro, usadas = elementos.homografia(imagem, pagina_layout)
    # a homografia leva mm para pixels da imagem; a imagem alinhada precisa de pixels para mm x ESCALA
    inversa = np.diag([ESCALA, ESCALA, 1.0]) @ np.linalg.inv(matriz)
    alinhada = cv2.warpPerspective(imagem, inversa, (LARGURA_PX, ALTURA_PX), flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=255)
    metodo = ELEMENTOS if usadas else APROXIMADO
    return PaginaAlinhada(imagem=alinhada, girada=girada, metodo=metodo, erro_mm=erro, caixas_usadas=usadas,
                          origem=imagem, matriz=inversa)


def _endireitar(imagem: np.ndarray) -> np.ndarray:
    """Corrige a inclinação pela borda de cima do QR code.

    As linhas das caixas são procuradas como traços horizontais longos; numa
    página inclinada 1 grau, uma linha de 170 mm sobe ou desce 3 mm de uma ponta
    à outra e deixa de ser horizontal para essa busca.
    """
    qr = elementos.cantos_do_qr(imagem)
    if qr is None:
        return imagem
    angulo = float(np.degrees(np.arctan2(qr[1][1] - qr[0][1], qr[1][0] - qr[0][0])))
    if abs(angulo) < 0.1 or abs(angulo) > 20:
        return imagem
    altura, largura = imagem.shape[:2]
    matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), angulo, 1.0)
    return cv2.warpAffine(imagem, matriz, (largura, altura), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=255)


def erro_das_caixas(alinhada: np.ndarray, pagina_layout) -> tuple[float | None, int]:
    """Na página já alinhada, a distância média, em mm, entre os cantos das caixas encontradas e os esperados.

    No alinhamento pelas marcas, as caixas não entram no cálculo e servem de
    conferência independente. No alinhamento pelos elementos, elas entram, e a
    medida é o erro do próprio ajuste.
    """
    erros = []
    for caixa in pagina_layout.caixas:
        esperado = elementos.cantos_esperados_caixa(caixa) * ESCALA
        encontrado = elementos.localizar_caixa(alinhada, esperado, caixa, ESCALA)
        if encontrado is not None:
            erros.append(float(np.linalg.norm(encontrado - esperado, axis=1).mean() / ESCALA))
    return (float(np.mean(erros)) if erros else None), len(erros)


def alinhar_pelas_marcas(imagem: np.ndarray) -> PaginaAlinhada:
    """Alinha a página e confere a orientação pela posição do QR code.

    As quatro marcas são iguais, então elas sozinhas não dizem se a página está
    de cabeça para baixo. O QR code diz: primeiro pela detecção do OpenCV e,
    se ela falhar, pela quantidade de tinta onde o QR code deveria estar.
    """
    girada = _de_cabeca_para_baixo(imagem)
    primeira = cv2.rotate(imagem, cv2.ROTATE_180) if girada else imagem
    alinhada, matriz = _alinhar_nesta_posicao(primeira)
    origem = primeira
    if _tinta_no_qr(alinhada) < 0.25:
        invertida = cv2.rotate(primeira, cv2.ROTATE_180)
        try:
            outra = _alinhar_nesta_posicao(invertida)
        except AlinhamentoFalhou:
            outra = None
        if outra is not None and _tinta_no_qr(outra[0]) > _tinta_no_qr(alinhada):
            (alinhada, matriz), origem, girada = outra, invertida, not girada
    return PaginaAlinhada(imagem=alinhada, girada=girada, origem=origem, matriz=matriz)


def recorte(alinhada: np.ndarray, x: float, y: float, largura: float, altura: float, margem: float = 2.0) -> np.ndarray:
    """Região da página alinhada, em milímetros."""
    x0, y0 = max(0, round((x - margem) * ESCALA)), max(0, round((y - margem) * ESCALA))
    x1 = min(LARGURA_PX, round((x + largura + margem) * ESCALA))
    y1 = min(ALTURA_PX, round((y + altura + margem) * ESCALA))
    return alinhada[y0:y1, x0:x1]
