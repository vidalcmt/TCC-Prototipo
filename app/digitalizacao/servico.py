"""Folhas digitalizadas: recebimento, identificação pelo QR code e armazenamento.

O professor envia um PDF (por exemplo, a turma inteira digitalizada de uma
vez na copiadora) ou fotos das folhas. Cada página é convertida em imagem em
tons de cinza, o QR code é lido para saber de qual folha e de qual página se
trata, e a imagem é gravada em disco. A leitura das respostas nas imagens é
feita depois, em outra etapa.
"""

import uuid
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import config
from app.folhas import layout as L
from app.folhas.servico import normalizar_codigo
from app.models import Atividade, Folha, PaginaDigitalizada

EXTENSOES = {".pdf", ".png", ".jpg", ".jpeg"}
DPI = 200                    # suficiente para o QR code, as bolinhas e a letra à mão
LADO_MAXIMO = 3000           # fotos de celular são reduzidas a este tamanho
MAXIMO_PAGINAS = 150         # por envio
MAXIMO_BYTES = 80 * 1024 * 1024
QUALIDADE_JPEG = 90

IDENTIFICADA, SEM_QR, OUTRA_ATIVIDADE, SUBSTITUIDA = "identificada", "sem_qr", "outra_atividade", "substituida"
ROTULOS = {
    IDENTIFICADA: "Identificada", SEM_QR: "QR code não lido", OUTRA_ATIVIDADE: "De outra atividade",
    SUBSTITUIDA: "Substituída por uma mais nova",
}


class DigitalizacaoInvalida(ValueError):
    """Arquivo recusado, com a mensagem exibida ao professor."""


@dataclass
class ResumoEnvio:
    paginas: int = 0
    identificadas: int = 0
    sem_qr: int = 0
    outra_atividade: int = 0
    substituidas: int = 0
    recusados: list[str] = field(default_factory=list)

    def texto(self) -> str:
        partes = [f"{self.paginas} {'página recebida' if self.paginas == 1 else 'páginas recebidas'}",
                  f"{self.identificadas} identificadas pelo QR code"]
        if self.sem_qr:
            partes.append(f"{self.sem_qr} sem QR code legível (indique a folha abaixo)")
        if self.outra_atividade:
            partes.append(f"{self.outra_atividade} de outra atividade")
        if self.substituidas:
            partes.append(f"{self.substituidas} substituíram páginas enviadas antes")
        texto = "; ".join(partes) + "."
        if self.recusados:
            texto += " Arquivos recusados: " + "; ".join(self.recusados) + "."
        return texto


# ---------------------------------------------------------------------------
# Imagens
# ---------------------------------------------------------------------------

def imagens_do_arquivo(nome: str, conteudo: bytes) -> list[np.ndarray]:
    """Páginas do arquivo como imagens em tons de cinza."""
    extensao = Path(nome).suffix.lower()
    if extensao not in EXTENSOES:
        raise DigitalizacaoInvalida(f"{nome}: envie PDF, PNG ou JPG")
    if extensao == ".pdf":
        try:
            documento = pymupdf.open(stream=conteudo, filetype="pdf")
        except Exception:
            raise DigitalizacaoInvalida(f"{nome}: o PDF não pôde ser aberto")
        if documento.page_count > MAXIMO_PAGINAS:
            raise DigitalizacaoInvalida(f"{nome}: mais de {MAXIMO_PAGINAS} páginas; divida o arquivo")
        imagens = []
        for pagina in documento:
            pixels = pagina.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
            imagens.append(np.frombuffer(pixels.samples, dtype=np.uint8).reshape(pixels.h, pixels.w).copy())
        return imagens
    imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if imagem is None:
        raise DigitalizacaoInvalida(f"{nome}: a imagem não pôde ser aberta")
    maior = max(imagem.shape)
    if maior > LADO_MAXIMO:
        escala = LADO_MAXIMO / maior
        imagem = cv2.resize(imagem, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    return [imagem]


def ler_qr_da_imagem(imagem: np.ndarray) -> tuple[str, int] | None:
    """Procura o QR code da folha, tentando versões da imagem que ajudam em digitalizações ruins."""
    detector = cv2.QRCodeDetector()
    tentativas = [imagem]
    altura, largura = imagem.shape[:2]
    # O QR code fica no canto superior direito; o recorte ampliado ajuda quando ele sai pequeno.
    canto = imagem[: altura // 3, largura // 2:]
    tentativas.append(cv2.resize(canto, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
    # Página de cabeça para baixo: o QR code fica no canto inferior esquerdo.
    tentativas.append(cv2.resize(imagem[2 * altura // 3:, : largura // 2], None, fx=2, fy=2,
                                 interpolation=cv2.INTER_CUBIC))
    tentativas.append(cv2.threshold(imagem, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
    for versao in tentativas:
        try:
            texto, _, _ = detector.detectAndDecode(versao)
        except cv2.error:
            continue
        lido = L.ler_qr(texto)
        if lido is not None:
            return normalizar_codigo(lido[0]), lido[1]
    return None


def _gravar(imagem: np.ndarray, atividade_id: int) -> str:
    relativo = Path(f"atividade_{atividade_id}") / f"{uuid.uuid4().hex}.jpg"
    destino = Path(config.pasta_arquivos) / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(destino), imagem, [cv2.IMWRITE_JPEG_QUALITY, QUALIDADE_JPEG]):
        raise OSError(f"Não foi possível gravar {destino}")
    return relativo.as_posix()


def caminho(pagina: PaginaDigitalizada) -> Path:
    return Path(config.pasta_arquivos) / pagina.arquivo


# ---------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------

def _ocupar(sessao: Session, pagina: PaginaDigitalizada, folha: Folha, numero: int) -> bool:
    """Liga a página à folha. A digitalização mais nova da mesma página substitui a anterior.

    Devolve verdadeiro se alguma página anterior foi substituída.
    """
    anteriores = sessao.scalars(select(PaginaDigitalizada).where(
        PaginaDigitalizada.folha_id == folha.id, PaginaDigitalizada.pagina == numero,
        PaginaDigitalizada.situacao == IDENTIFICADA, PaginaDigitalizada.id != pagina.id,
    )).all()
    for anterior in anteriores:
        anterior.situacao = SUBSTITUIDA
    pagina.folha, pagina.pagina, pagina.situacao = folha, numero, IDENTIFICADA
    return bool(anteriores)


def receber(sessao: Session, atividade: Atividade, arquivos: list[tuple[str, bytes]],
            usuario_id: int | None) -> ResumoEnvio:
    resumo = ResumoEnvio()
    total = sum(len(c) for _, c in arquivos)
    if total > MAXIMO_BYTES:
        raise DigitalizacaoInvalida(f"Envio maior que {MAXIMO_BYTES // (1024 * 1024)} MB; divida em partes.")
    for nome, conteudo in arquivos:
        try:
            imagens = imagens_do_arquivo(nome, conteudo)
        except DigitalizacaoInvalida as erro:
            resumo.recusados.append(str(erro))
            continue
        for posicao, imagem in enumerate(imagens, start=1):
            pagina = PaginaDigitalizada(atividade_id=atividade.id, arquivo=_gravar(imagem, atividade.id),
                                        nome_original=nome[:300], pagina_do_arquivo=posicao,
                                        situacao=SEM_QR, usuario_id=usuario_id)
            sessao.add(pagina)
            resumo.paginas += 1
            lido = ler_qr_da_imagem(imagem)
            if lido is None:
                resumo.sem_qr += 1
                continue
            codigo, numero = lido
            folha = sessao.scalars(select(Folha).where(Folha.codigo == codigo)).first()
            if folha is None or folha.atividade_id != atividade.id:
                pagina.situacao = OUTRA_ATIVIDADE
                resumo.outra_atividade += 1
                continue
            sessao.flush()
            if _ocupar(sessao, pagina, folha, numero):
                resumo.substituidas += 1
            resumo.identificadas += 1
    sessao.commit()
    return resumo


def atribuir(sessao: Session, pagina: PaginaDigitalizada, atividade: Atividade, codigo: str, numero: int,
             paginas_da_folha: int) -> None:
    """O professor indica a folha de uma página cujo QR code não foi lido."""
    procurado = normalizar_codigo(codigo)
    folha = next((f for f in atividade.folhas if f.codigo == procurado), None)
    if folha is None:
        raise DigitalizacaoInvalida(f"Nenhuma folha desta atividade tem o código {procurado}.")
    if not 1 <= numero <= paginas_da_folha:
        raise DigitalizacaoInvalida(f"A folha tem {paginas_da_folha} {'página' if paginas_da_folha == 1 else 'páginas'}.")
    _ocupar(sessao, pagina, folha, numero)
    sessao.commit()


def excluir(sessao: Session, pagina: PaginaDigitalizada) -> None:
    arquivo = caminho(pagina)
    sessao.delete(pagina)
    sessao.commit()
    arquivo.unlink(missing_ok=True)


def paginas_da_atividade(sessao: Session, atividade: Atividade) -> list[PaginaDigitalizada]:
    return sessao.scalars(select(PaginaDigitalizada).where(PaginaDigitalizada.atividade_id == atividade.id)
                          .order_by(PaginaDigitalizada.id)).all()


def tem_digitalizacoes(sessao: Session, atividade: Atividade) -> bool:
    return sessao.scalar(select(PaginaDigitalizada.id).where(PaginaDigitalizada.atividade_id == atividade.id)
                         .limit(1)) is not None
