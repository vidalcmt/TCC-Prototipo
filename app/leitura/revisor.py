"""Revisão da transcrição da escrita por um modelo de linguagem que vê a imagem.

O OCR erra de um jeito que nenhuma pessoa erraria: lê "um organismo" como
"vim organizmo", porque a letra "u" parece um "v". Um modelo que vê a imagem
da caixa e o texto lido consegue desfazer essas trocas. O risco é ele corrigir
também os erros do próprio aluno, e a correção avaliaria então um texto que o
aluno não escreveu. Por isso:

- o modelo recebe só a imagem da caixa e o texto lido, e nunca o enunciado ou
  a resposta esperada, para não puxar o texto para a resposta certa;
- o prompt (prompts/transcricao/v1.md) separa erro de leitura de erro do aluno
  e manda manter o segundo;
- cada mudança volta listada, e a página da folha mostra ao professor o que
  foi trocado, antes de ele salvar;
- uma revisão que muda demais o texto é descartada, e fica o texto do OCR.

A revisão é ligada com LEITURA_REVISAO_IA=true. Cada caixa com texto é uma
chamada ao modelo, registrada nas métricas e contada no limite diário.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np
from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import config
from app.contas.sessao import chamadas_hoje
from app.correcao.contratos import RevisaoTranscricaoV1
from app.correcao.llm import chamar_modelo
from app.correcao.prompts import carregar_prompt
from app.leitura.medida import taxa_de_erro

PROMPT = ("transcricao", 1)
LADO_MAXIMO_PX = 1600
MUDANCA_MAXIMA = 0.4  # fração do texto; acima disso, a revisão é descartada


@dataclass
class Revisao:
    texto: str
    alteracoes: list[dict] = field(default_factory=list)
    incertos: list[str] = field(default_factory=list)
    descartada: str | None = None   # motivo, quando o texto do OCR foi mantido


def _jpeg(recorte: np.ndarray) -> bytes:
    maior = max(recorte.shape[:2])
    if maior > LADO_MAXIMO_PX:
        escala = LADO_MAXIMO_PX / maior
        recorte = cv2.resize(recorte, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", recorte, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes()


def ligada() -> bool:
    return config.leitura_revisao_ia


def revisar(sessao: Session, recorte: np.ndarray, texto_ocr: str, cliente: OpenAI | None = None,
            usuario_id: int | None = None) -> Revisao:
    """Revisa o texto de uma caixa. Em qualquer falha, devolve o texto do OCR, com o motivo."""
    if not texto_ocr.strip():
        return Revisao(texto=texto_ocr)
    if usuario_id is not None and chamadas_hoje(sessao, usuario_id) >= config.limite_chamadas_dia:
        return Revisao(texto=texto_ocr, descartada="limite diário de chamadas atingido")
    resultado = chamar_modelo(
        sessao, carregar_prompt(*PROMPT), RevisaoTranscricaoV1, {"texto_ocr": texto_ocr},
        tipo_questao="transcricao", cliente=cliente, usuario_id=usuario_id, imagem_jpeg=_jpeg(recorte),
    )
    if not resultado.sucesso:
        return Revisao(texto=texto_ocr, descartada="falha na chamada ao modelo")
    saida = resultado.saida
    texto = " ".join(saida.texto.split())
    if not texto:
        # Uma caixa vazia vale zero sem passar pela correção: a decisão fica com o professor.
        return Revisao(texto=texto_ocr, incertos=[texto_ocr],
                       descartada="a revisão considerou a caixa em branco; confira com a imagem")
    mudanca = taxa_de_erro(texto, texto_ocr)
    if mudanca > MUDANCA_MAXIMA:
        resultado.metrica.sucesso = False
        resultado.metrica.motivo_falha = f"revisão descartada: mudou {mudanca:.0%} do texto"
        sessao.commit()
        return Revisao(texto=texto_ocr, descartada=f"a revisão mudou {mudanca:.0%} do texto, mais do que o permitido")
    return Revisao(
        texto=texto,
        alteracoes=[a.model_dump() for a in saida.alteracoes if a.lido != a.corrigido],
        incertos=[t for t in saida.trechos_incertos if t.strip()],
    )
