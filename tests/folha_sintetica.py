"""Folhas de resposta desenhadas em imagem, com o layout real, para testar a leitura.

Simulam o que sai de uma impressão seguida de digitalização: bolinhas
preenchidas a caneta, um X, escrita nas caixas, inclinação, perspectiva,
ruído e página de cabeça para baixo.
"""

import cv2
import numpy as np
import qrcode

from app.folhas import layout as L

DPI = 200
MM = DPI / 25.4


def _p(v):
    return round(v * MM)


def _matriz_qr(texto):
    qr = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(texto)
    qr.make(fit=True)
    return np.array(qr.get_matrix(), dtype=bool)


def desenhar(pagina, codigo: str | None, marcas: dict | None = None, escrita: dict | None = None) -> np.ndarray:
    """marcas: {(questao_id): letra ou [letras] ou ("x", letra) ou ("fraca", letra)}; escrita: {(questao_id, item): texto}."""
    img = np.full((_p(L.ALTURA), _p(L.LARGURA)), 255, np.uint8)
    for x, y in L.MARCAS:
        img[_p(y):_p(y + L.MARCA), _p(x):_p(x + L.MARCA)] = 0
    if codigo:
        lado = _p(L.QR_LADO)
        modulo = cv2.resize((~_matriz_qr(L.conteudo_qr(codigo, pagina.numero)) * 255).astype(np.uint8), (lado, lado),
                            interpolation=cv2.INTER_NEAREST)
        img[_p(L.QR_Y):_p(L.QR_Y) + lado, _p(L.QR_X):_p(L.QR_X) + lado] = modulo
        cv2.putText(img, codigo, (_p(24), _p(32)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
    for b in pagina.bolhas:
        cv2.circle(img, (_p(b.x), _p(b.y)), _p(b.r), 0, 2, cv2.LINE_AA)
        cv2.putText(img, b.letra, (_p(b.x - 1.0), _p(b.y + 1.0)), cv2.FONT_HERSHEY_SIMPLEX, 0.32, 102, 1, cv2.LINE_AA)
    for c in pagina.caixas:
        cv2.rectangle(img, (_p(c.x), _p(c.y)), (_p(c.x + c.largura), _p(c.y + c.altura)), 0, 2)
        for k in range(1, c.linhas):
            y = _p(c.y + k * L.LINHA_RESPOSTA)
            cv2.line(img, (_p(c.x + 3), y), (_p(c.x + c.largura - 3), y), 185, 1)
    rng = np.random.default_rng(3)
    for b in pagina.bolhas:
        marca = (marcas or {}).get(b.questao_id)
        if marca is None:
            continue
        tipo, letras = ("cheia", [marca]) if isinstance(marca, str) else (
            ("cheia", marca) if isinstance(marca, list) else (marca[0], [marca[1]]))
        if b.letra not in letras:
            continue
        centro, raio = (_p(b.x), _p(b.y)), _p(b.r)
        if tipo == "cheia":  # caneta: preenchimento irregular, um pouco menor que o círculo
            cv2.ellipse(img, centro, (int(raio * 0.92), int(raio * 0.85)), rng.uniform(0, 180), 0, 360, 25, -1)
        elif tipo == "x":
            d = int(raio * 0.8)
            cv2.line(img, (centro[0] - d, centro[1] - d), (centro[0] + d, centro[1] + d), 30, 4)
            cv2.line(img, (centro[0] - d, centro[1] + d), (centro[0] + d, centro[1] - d), 30, 4)
        elif tipo == "fraca":
            cv2.circle(img, centro, int(raio * 0.55), 40, -1)
    for c in pagina.caixas:
        texto = (escrita or {}).get((c.questao_id, c.item))
        if texto:
            cv2.putText(img, texto, (_p(c.x + 4), _p(c.y + L.LINHA_RESPOSTA - 1.5)), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX,
                        0.9, 20, 2, cv2.LINE_AA)
    return img


def digitalizar(img: np.ndarray, angulo=1.5, perspectiva=0.01, girar=False, ruido=8, semente=5) -> np.ndarray:
    """Inclinação, perspectiva, margem de fundo, borrão, ruído e compressão JPEG."""
    rng = np.random.default_rng(semente)
    h, w = img.shape
    borda = 60
    grande = cv2.copyMakeBorder(img, borda, borda, borda, borda, cv2.BORDER_CONSTANT, value=230)
    H, W = grande.shape
    origem = np.float32([[0, 0], [W, 0], [0, H], [W, H]])
    desvio = perspectiva * W
    destino = origem + rng.uniform(-desvio, desvio, origem.shape).astype(np.float32)
    grande = cv2.warpPerspective(grande, cv2.getPerspectiveTransform(origem, destino), (W, H), borderValue=220)
    grande = cv2.warpAffine(grande, cv2.getRotationMatrix2D((W / 2, H / 2), angulo, 0.97), (W, H), borderValue=220)
    grande = cv2.GaussianBlur(grande, (3, 3), 0)
    grande = np.clip(grande.astype(np.float32) * 0.93 + 8 + rng.normal(0, ruido, grande.shape), 0, 255).astype(np.uint8)
    if girar:
        grande = cv2.rotate(grande, cv2.ROTATE_180)
    return cv2.imdecode(cv2.imencode(".jpg", grande, [cv2.IMWRITE_JPEG_QUALITY, 75])[1], cv2.IMREAD_GRAYSCALE)
