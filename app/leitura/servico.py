"""Leitura automática das folhas digitalizadas e preenchimento da conferência.

Para cada página identificada: alinha pelas marcas dos cantos, lê as
bolinhas e, se houver caixas de discursivas na página e o Google Cloud
Vision estiver configurado, transcreve a escrita. O resultado não vira
resposta sozinho: ele preenche o formulário da folha, e o professor confere
e salva. Só então as respostas existem.
"""

import json
from pathlib import Path

import cv2
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import config
from app.digitalizacao.servico import IDENTIFICADA, caminho
from app.folhas import layout as L
from app.leitura import ocr
from app.leitura.alinhamento import AlinhamentoFalhou, alinhar, recorte
from app.leitura.bolhas import ler_bolhas
from app.models import Atividade, Folha, LeituraPagina, PaginaDigitalizada, agora

LIDA, FALHA = "lida", "falha"


def paginas_do_layout(atividade: Atividade) -> list:
    return L.montar(atividade, atividade.linhas_por_resposta)


def ler_pagina(sessao: Session, pagina: PaginaDigitalizada, usuario_id: int | None,
               http: httpx.Client | None = None) -> LeituraPagina:
    """Lê (ou lê de novo) uma página identificada. Uma leitura anterior é substituída."""
    atividade = sessao.get(Atividade, pagina.atividade_id)
    if pagina.leitura is not None:
        _apagar_alinhada(pagina.leitura)
        sessao.delete(pagina.leitura)
        sessao.flush()
    leitura = LeituraPagina(pagina_digitalizada=pagina, situacao=FALHA, usuario_id=usuario_id)
    sessao.add(leitura)

    layout = paginas_do_layout(atividade)
    if pagina.pagina is None or not 1 <= pagina.pagina <= len(layout):
        leitura.motivo = "A página não corresponde ao layout da folha."
        sessao.commit()
        return leitura
    pagina_layout = layout[pagina.pagina - 1]

    imagem = cv2.imread(str(caminho(pagina)), cv2.IMREAD_GRAYSCALE)
    if imagem is None:
        leitura.motivo = "O arquivo da imagem não foi encontrado."
        sessao.commit()
        return leitura
    try:
        alinhada = alinhar(imagem).imagem
    except AlinhamentoFalhou as erro:
        leitura.motivo = str(erro)
        sessao.commit()
        return leitura

    relativo = Path(pagina.arquivo).with_name(Path(pagina.arquivo).stem + "_alinhada.jpg")
    cv2.imwrite(str(Path(config.pasta_arquivos) / relativo), alinhada, [cv2.IMWRITE_JPEG_QUALITY, 90])
    leitura.arquivo_alinhado = relativo.as_posix()

    objetivas = {str(qid): {"marcada": l.marcada, "duvida": l.duvida, "preenchimento": l.preenchimento}
                 for qid, l in ler_bolhas(alinhada, pagina_layout).items()}
    textos, avisos = {}, []
    if pagina_layout.caixas:
        try:
            anotacao, leitura.latencia_ocr_ms = ocr.anotar(alinhada, http)
            leitura.servico_ocr = ocr.SERVICO
            textos = ocr.textos_por_caixa(anotacao, pagina_layout.caixas)
        except ocr.OcrIndisponivel as erro:
            avisos.append(str(erro))
        except ocr.OcrFalhou as erro:
            avisos.append(str(erro))
    leitura.resultado_json = json.dumps({"objetivas": objetivas, "textos": textos}, ensure_ascii=False)
    leitura.situacao = LIDA
    leitura.motivo = " ".join(avisos) or None
    sessao.commit()
    return leitura


def _apagar_alinhada(leitura: LeituraPagina) -> None:
    if leitura.arquivo_alinhado:
        (Path(config.pasta_arquivos) / leitura.arquivo_alinhado).unlink(missing_ok=True)


def paginas_para_ler(sessao: Session, atividade: Atividade) -> list[PaginaDigitalizada]:
    return [p for p in sessao.scalars(
        select(PaginaDigitalizada).where(PaginaDigitalizada.atividade_id == atividade.id,
                                         PaginaDigitalizada.situacao == IDENTIFICADA)
        .order_by(PaginaDigitalizada.id)) if p.leitura is None]


def leituras_da_folha(folha: Folha) -> list[LeituraPagina]:
    return [p.leitura for p in folha.digitalizacoes if p.situacao == IDENTIFICADA and p.leitura is not None]


def valores_lidos(folha: Folha) -> tuple[dict[str, str], set[str], list[str], bool]:
    """O que preencher no formulário da folha.

    Devolve os valores por campo do formulário, os campos duvidosos, os avisos
    das leituras e se há leitura ainda não conferida pelo professor.
    """
    valores, duvidas, avisos, pendente = {}, set(), [], False
    for leitura in leituras_da_folha(folha):
        numero = leitura.pagina_digitalizada.pagina
        if leitura.situacao == FALHA:
            avisos.append(f"Página {numero}: {leitura.motivo}")
            continue
        if leitura.motivo:
            # o aviso de chave ausente é o mesmo em todas as páginas: aparece uma vez só
            aviso = leitura.motivo if "GOOGLE_VISION_API_KEY" in leitura.motivo else f"Página {numero}: {leitura.motivo}"
            if aviso not in avisos:
                avisos.append(aviso)
        pendente = pendente or leitura.conferida_em is None
        resultado = json.loads(leitura.resultado_json)
        for qid, lido in resultado.get("objetivas", {}).items():
            valores[f"q{qid}"] = lido["marcada"]
            if lido["duvida"] or lido["marcada"] == "multipla":
                duvidas.add(f"q{qid}")
        for campo, texto in resultado.get("textos", {}).items():
            valores[campo] = texto
    return valores, duvidas, avisos, pendente


def marcar_conferidas(sessao: Session, folha: Folha) -> None:
    """Chamado quando o professor salva o formulário da folha."""
    for leitura in leituras_da_folha(folha):
        if leitura.situacao == LIDA and leitura.conferida_em is None:
            leitura.conferida_em = agora()
    sessao.commit()


def recorte_da_caixa(folha: Folha, campo: str):
    """Imagem da caixa de resposta de um campo, recortada da página alinhada."""
    layout = paginas_do_layout(folha.atividade)
    for pagina_digitalizada in folha.digitalizacoes:
        leitura = pagina_digitalizada.leitura
        if pagina_digitalizada.situacao != IDENTIFICADA or leitura is None or not leitura.arquivo_alinhado:
            continue
        if not 1 <= (pagina_digitalizada.pagina or 0) <= len(layout):
            continue
        for caixa in layout[pagina_digitalizada.pagina - 1].caixas:
            if ocr.campo_da_caixa(caixa) == campo:
                imagem = cv2.imread(str(Path(config.pasta_arquivos) / leitura.arquivo_alinhado), cv2.IMREAD_GRAYSCALE)
                if imagem is None:
                    return None
                return recorte(imagem, caixa.x, caixa.y, caixa.largura, caixa.altura)
    return None


def campos_com_recorte(folha: Folha) -> set[str]:
    layout = paginas_do_layout(folha.atividade)
    campos = set()
    for p in folha.digitalizacoes:
        if p.situacao == IDENTIFICADA and p.leitura is not None and p.leitura.arquivo_alinhado \
                and 1 <= (p.pagina or 0) <= len(layout):
            campos.update(ocr.campo_da_caixa(c) for c in layout[p.pagina - 1].caixas)
    return campos
