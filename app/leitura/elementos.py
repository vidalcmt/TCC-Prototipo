"""Alinhamento pela própria folha, quando as marcas dos cantos não aparecem.

As marcas pretas dos cantos são o jeito mais simples de endireitar a página,
mas uma folha impressa sem elas (por exemplo, numa impressora que não imprime
cores de fundo) ainda tem outros elementos em posições conhecidas: o QR code,
com os seus quatro cantos, e o contorno de cada caixa de resposta. Cada um
desses cantos é um par de pontos: onde ele está na imagem e onde ele deveria
estar na folha, em milímetros. Com quatro pares ou mais, calcula-se a mesma
transformação de perspectiva (homografia) usada com as marcas.

Os cantos do QR code ficam muito próximos uns dos outros, num quadrado de
26 mm; sozinhos, eles erram muito longe dele. As caixas espalham os pontos
pela página e tornam o alinhamento preciso. Por isso o método procura ao menos
uma caixa, e a qualidade do resultado é medida e guardada. Sem nenhuma caixa,
resta um alinhamento aproximado pelas bordas da imagem.
"""

import cv2
import numpy as np

from app.folhas import layout as L

PROPORCAO_A4 = L.ALTURA / L.LARGURA
TOLERANCIA_CENTRO_MM = 20.0  # distância máxima entre a caixa prevista e a encontrada
LIMIAR_RANSAC_MM = 3.0
# Fração da faixa que precisa estar escura para contar como borda. A escrita
# raramente passa disso numa linha inteira; a distância entre as bordas filtra o resto.
LIMIAR_LINHA = 0.45


class ElementosInsuficientes(ValueError):
    pass


def cantos_esperados_qr() -> np.ndarray:
    x, y, lado = L.QR_X, L.QR_Y, L.QR_LADO
    return np.float32([(x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado)])


def cantos_esperados_caixa(caixa) -> np.ndarray:
    return np.float32([(caixa.x, caixa.y), (caixa.x + caixa.largura, caixa.y),
                       (caixa.x + caixa.largura, caixa.y + caixa.altura), (caixa.x, caixa.y + caixa.altura)])


def cantos_do_qr(imagem: np.ndarray) -> np.ndarray | None:
    """Os quatro cantos do QR code da folha, na ordem do próprio código (superior esquerdo primeiro).

    Como a ordem segue o código e não a imagem, a homografia já desfaz uma
    página girada. Tenta a imagem inteira e recortes ampliados ou reduzidos dos
    cantos onde o QR code pode estar, como na identificação das páginas.
    """
    detector = cv2.QRCodeDetector()
    altura, largura = imagem.shape[:2]
    tentativas = [(imagem, 0, 0, 1.0)]
    for y0, y1, x0, x1 in [(0, altura // 3, largura // 2, largura), (2 * altura // 3, altura, 0, largura // 2)]:
        for fator in (1.0, 0.5, 2.0):
            parte = imagem[y0:y1, x0:x1]
            interpolacao = cv2.INTER_AREA if fator < 1 else cv2.INTER_CUBIC
            tentativas.append((cv2.resize(parte, None, fx=fator, fy=fator, interpolation=interpolacao), x0, y0, fator))
    tentativas.append((cv2.resize(imagem, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA), 0, 0, 0.5))
    for versao, x0, y0, fator in tentativas:
        try:
            texto, pontos, _ = detector.detectAndDecode(versao)
        except cv2.error:
            continue
        if texto.startswith("DEVOLUTIVA|") and pontos is not None:
            return (pontos.reshape(4, 2) / fator + np.float32([x0, y0])).astype(np.float32)
    return None


def _centros_de_faixas(mascara: np.ndarray) -> list[float]:
    """Centros das sequências de posições verdadeiras (as linhas encontradas num perfil)."""
    centros, inicio = [], None
    for k, valor in enumerate(list(mascara) + [False]):
        if valor and inicio is None:
            inicio = k
        elif not valor and inicio is not None:
            centros.append((inicio + k - 1) / 2)
            inicio = None
    return centros


def _melhor_par(posicoes: list[float], inicio: float, fim: float, tamanho_mm: float, mm: float,
                dentro_mm: float = 8.0, fora_mm: float = 16.0):
    """Entre as linhas encontradas, o par (início, fim) que melhor forma a caixa.

    O par precisa estar perto da posição prevista e ter a distância certa entre
    as duas bordas. Só a posição não basta: a borda de baixo da caixa anterior
    fica 11 mm acima da borda de cima desta, e as linhas de escrita, a cada 8 mm.
    A tolerância no tamanho (8%) cobre digitalizações esticadas numa direção,
    comuns em aplicativos de celular que ajustam a imagem ao formato A4.
    """
    melhor, nota_melhor = None, None
    for a in posicoes:
        if not inicio - fora_mm * mm <= a <= inicio + dentro_mm * mm:
            continue
        for b in posicoes:
            if not fim - dentro_mm * mm <= b <= fim + fora_mm * mm or b <= a:
                continue
            diferenca = abs((b - a) / mm - tamanho_mm)
            if diferenca > max(3.0, 0.08 * tamanho_mm):
                continue
            nota = diferenca + 0.3 * abs(a - inicio) / mm
            if nota_melhor is None or nota < nota_melhor:
                melhor, nota_melhor = (a, b), nota
    return melhor


def localizar_caixa(imagem: np.ndarray, previsto: np.ndarray, caixa, px_por_mm: float) -> np.ndarray | None:
    """Procura a borda da caixa perto da posição prevista e devolve os quatro cantos, em pixels.

    Usa perfis de tinta: numa faixa larga do meio da caixa, a borda de cima e a
    de baixo são linhas escuras que atravessam quase toda a largura, o que a
    escrita do aluno nunca faz; nas laterais, as bordas verticais atravessam
    toda a altura. Entre as linhas encontradas, fica o par com a distância certa
    entre si e mais perto da posição prevista. A previsão pode
    errar até cerca de 15 mm.
    """
    altura_img, largura_img = imagem.shape[:2]
    mm = px_por_mm
    x0, y0 = previsto[:, 0].min(), previsto[:, 1].min()
    x1, y1 = previsto[:, 0].max(), previsto[:, 1].max()
    papel = float(np.percentile(imagem, 90))
    escura = (imagem < papel * 0.7).astype(np.uint8)
    # Uma linha levemente torta ocupa algumas linhas de pixels; engrossar 1 mm
    # na direção perpendicular faz o perfil enxergá-la inteira.
    faixa_mm = max(3, int(round(1.2 * mm)))
    engrossada_v = cv2.dilate(escura, np.ones((faixa_mm, 1), np.uint8))
    engrossada_h = cv2.dilate(escura, np.ones((1, faixa_mm), np.uint8))

    def faixa(a, b, limite):
        return max(0, int(a)), min(limite, int(b))

    ya, yb = faixa(y0 - 18 * mm, y1 + 18 * mm, altura_img)
    xa, xb = faixa(x0 + 15 * mm, x1 - 15 * mm, largura_img)
    if yb - ya < 10 or xb - xa < 10:
        return None
    linhas = [ya + c for c in _centros_de_faixas(engrossada_v[ya:yb, xa:xb].mean(axis=1) > LIMIAR_LINHA)]
    par = _melhor_par(linhas, y0, y1, caixa.altura, mm)
    if par is None:
        return None
    topo, base = par

    ya, yb = faixa(topo + 2 * mm, base - 2 * mm, altura_img)
    xa, xb = faixa(x0 - 18 * mm, x1 + 18 * mm, largura_img)
    if yb - ya < 10:
        return None
    colunas = [xa + c for c in _centros_de_faixas(engrossada_h[ya:yb, xa:xb].mean(axis=0) > LIMIAR_LINHA)]
    # sem linhas verticais dentro da caixa, a busca das laterais pode ir mais para dentro
    par = _melhor_par(colunas, x0, x1, caixa.largura, mm, dentro_mm=25.0)
    if par is None:
        return None
    esquerda, direita = par
    return np.float32([(esquerda, topo), (direita, topo), (direita, base), (esquerda, base)])


def _prever(matriz_mm_para_px: np.ndarray, pontos_mm: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(pontos_mm[None], matriz_mm_para_px)[0]


def erro_medio_mm(matriz_mm_para_px: np.ndarray, pontos_mm: np.ndarray, pontos_px: np.ndarray,
                  px_por_mm: float) -> float:
    return float(np.linalg.norm(_prever(matriz_mm_para_px, pontos_mm) - pontos_px, axis=1).mean() / px_por_mm)


def palpite_inicial(imagem: np.ndarray, qr: np.ndarray) -> np.ndarray:
    """Primeira estimativa, só para encontrar as caixas.

    Se a imagem tem a proporção de uma folha A4, como nas digitalizações e nos
    aplicativos que recortam a folha, as bordas da imagem são as da folha.
    Senão, usa o QR code sozinho.
    """
    altura, largura = imagem.shape[:2]
    if abs(altura / largura - PROPORCAO_A4) < 0.05 * PROPORCAO_A4:
        folha = np.float32([(0, 0), (L.LARGURA, 0), (L.LARGURA, L.ALTURA), (0, L.ALTURA)])
        return cv2.getPerspectiveTransform(folha, np.float32([(0, 0), (largura, 0), (largura, altura), (0, altura)]))
    return cv2.getPerspectiveTransform(cantos_esperados_qr(), qr)


def correspondencias(imagem: np.ndarray, pagina_layout, qr: np.ndarray) -> tuple[list, float]:
    """Pares (cantos esperados em mm, cantos encontrados em pixels) de cada caixa encontrada."""
    px_por_mm = float(np.linalg.norm(qr[1] - qr[0]) / L.QR_LADO)
    matriz = palpite_inicial(imagem, qr)
    melhores: list = []
    for _ in range(2):  # a segunda volta parte do alinhamento da primeira e acha as caixas que faltaram
        pares = []
        for caixa in pagina_layout.caixas:
            esperado = cantos_esperados_caixa(caixa)
            encontrado = localizar_caixa(imagem, _prever(matriz, esperado), caixa, px_por_mm)
            if encontrado is not None:
                pares.append((esperado, encontrado))
        if len(pares) >= len(melhores):
            melhores = pares
        if pares:
            origem = np.vstack([cantos_esperados_qr()] + [e for e, _ in pares])
            destino = np.vstack([qr] + [c for _, c in pares])
            nova, _ = cv2.findHomography(origem, destino, cv2.RANSAC, LIMIAR_RANSAC_MM * px_por_mm)
            if nova is not None:
                matriz = nova
    return melhores, px_por_mm


def homografia(imagem: np.ndarray, pagina_layout) -> tuple[np.ndarray, float | None, int]:
    """Transformação da folha (mm) para a imagem (pixels), o erro do ajuste em mm e quantas caixas foram usadas.

    Sem nenhuma caixa encontrada, e só se a imagem tem a proporção de uma
    folha A4 (a folha recortada pelo aplicativo ou pelo scanner), usa as bordas
    da imagem como se fossem as da folha. É um alinhamento aproximado, com erro
    de alguns milímetros, e é devolvido sem medida de erro e com zero caixas.
    """
    qr = cantos_do_qr(imagem)
    if qr is None:
        raise ElementosInsuficientes("Sem as marcas dos cantos, o alinhamento precisa do QR code, que não foi lido.")
    pares, px_por_mm = correspondencias(imagem, pagina_layout, qr)
    if not pares:
        altura, largura = imagem.shape[:2]
        if abs(altura / largura - PROPORCAO_A4) < 0.05 * PROPORCAO_A4:
            return palpite_inicial(imagem, qr), None, 0
        raise ElementosInsuficientes("Sem as marcas dos cantos, o alinhamento precisa de ao menos uma caixa de "
                                     "resposta, e nenhuma foi encontrada.")
    origem = np.vstack([cantos_esperados_qr()] + [e for e, _ in pares])
    destino = np.vstack([qr] + [c for _, c in pares])
    matriz, _ = cv2.findHomography(origem, destino, cv2.RANSAC, LIMIAR_RANSAC_MM * px_por_mm)
    if matriz is None:
        raise ElementosInsuficientes("Os elementos encontrados não permitem alinhar a página.")
    return matriz, erro_medio_mm(matriz, origem, destino, px_por_mm), len(pares)
