"""Regras das folhas de resposta: geração dos códigos, QR code e trava do layout."""

import re
import secrets

import qrcode
import qrcode.image.svg
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.folhas.layout import maximo_de_linhas
from app.models import Atividade, Folha

# Sem letras e números que se confundem à mão ou na leitura (0/O, 1/I/L).
ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TAMANHO_CODIGO = 8
MAXIMO_POR_VEZ = 200


class FolhasInvalidas(ValueError):
    """Pedido de geração recusado, com a mensagem exibida ao professor."""


def novo_codigo() -> str:
    """Código no formato XXXX-XXXX: 31^8, cerca de 850 bilhões de combinações."""
    bruto = "".join(secrets.choice(ALFABETO) for _ in range(TAMANHO_CODIGO))
    return f"{bruto[:4]}-{bruto[4:]}"


def normalizar_codigo(texto: str) -> str:
    """Aceita o código digitado com minúsculas, espaços ou sem o hífen."""
    limpo = "".join(c for c in (texto or "").upper() if c.isalnum())
    return f"{limpo[:4]}-{limpo[4:]}" if len(limpo) == TAMANHO_CODIGO else limpo


def gerar_folhas(sessao: Session, atividade: Atividade, quantidade: int, linhas: int) -> list[Folha]:
    """Cria mais `quantidade` folhas, numeradas depois das existentes.

    As linhas por resposta só podem ser escolhidas na primeira geração: as
    folhas seguintes precisam ter o mesmo layout das que já foram impressas.
    """
    if not atividade.itens:
        raise FolhasInvalidas("Adicione questões à atividade antes de gerar as folhas de resposta.")
    if not 1 <= quantidade <= MAXIMO_POR_VEZ:
        raise FolhasInvalidas(f"Informe uma quantidade de 1 a {MAXIMO_POR_VEZ} folhas.")
    if not atividade.folhas:
        if not 1 <= linhas <= maximo_de_linhas():
            raise FolhasInvalidas(f"As linhas por resposta vão de 1 a {maximo_de_linhas()}.")
        atividade.linhas_por_resposta = linhas

    existentes = set(sessao.scalars(select(Folha.codigo)))
    proximo = max((f.numero for f in atividade.folhas), default=0) + 1
    novas = []
    for numero in range(proximo, proximo + quantidade):
        codigo = novo_codigo()
        while codigo in existentes:
            codigo = novo_codigo()
        existentes.add(codigo)
        folha = Folha(numero=numero, codigo=codigo)
        atividade.folhas.append(folha)
        novas.append(folha)
    sessao.commit()
    return novas


def questoes_travadas(atividade: Atividade) -> bool:
    """Com folhas geradas, mudar as questões mudaria o layout das folhas já impressas."""
    return bool(atividade.folhas)


def descartar_folhas(sessao: Session, atividade: Atividade) -> None:
    atividade.folhas.clear()
    sessao.commit()


def qr_svg(texto: str) -> str:
    """QR code como SVG em linha, sem tamanho fixo: quem o usa define as medidas."""
    imagem = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=0,
                         error_correction=qrcode.constants.ERROR_CORRECT_M)
    svg = imagem.to_string(encoding="unicode")
    # O SVG gerado traz largura e altura em mm calculadas pela biblioteca; a folha usa as próprias.
    return re.sub(r'\s(width|height)="[^"]*"', "", svg, count=2)
