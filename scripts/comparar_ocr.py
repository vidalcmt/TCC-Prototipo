"""Compara o Google Cloud Vision e o Google Document AI nas mesmas folhas.

Uso:
    python -m scripts.comparar_ocr
    python -m scripts.comparar_ocr --csv comparacao.csv
    python -m scripts.comparar_ocr --revisao --sem-texto --csv comparacao.csv

Para cada página digitalizada cuja leitura já foi conferida e salva pelo
professor, alinha a imagem de novo, envia a mesma página aos dois serviços e
compara o texto de cada caixa com a resposta salva, que é a referência. Como a
letra, a imagem e o alinhamento são os mesmos, a diferença entre as taxas de
erro (CER e WER) é efeito só do serviço.

Com --revisao, o texto de cada serviço também passa pela revisão da IA
(app/leitura/revisor.py), e o resultado entra como uma terceira e uma quarta
condição ("vision+revisao", "documentai+revisao"), sempre contra a mesma
referência. Cada caixa com texto é uma chamada ao modelo, registrada nas
métricas.

Com --sem-texto, entram só as páginas conferidas sem o texto lido, em que o
professor digitou as respostas a partir da imagem. É a referência sem a
influência de nenhum dos serviços, e a que deve ir para o artigo.

Não altera nenhuma leitura nem resposta. Gasta uma página de cada serviço por
página digitalizada (as primeiras 1.000 por mês são gratuitas nos dois).
Os dois precisam estar configurados no .env: GOOGLE_VISION_API_KEY e
DOCUMENTAI_PROCESSADOR.
"""

import argparse
import csv
import sys

import cv2
from sqlalchemy import select

from app.digitalizacao.servico import IDENTIFICADA, caminho
from app.leitura import ocr
from app.leitura.alinhamento import AlinhamentoFalhou, alinhar
from app.leitura.servico import _revisar, paginas_do_layout
from app.models import LeituraPagina, PaginaDigitalizada
from scripts.medir_leitura import taxa_de_erro

SERVICOS = ("vision", "documentai")


def referencia(folha, campo: str) -> str | None:
    """O texto salvo pelo professor para o campo, ou None se não há resposta salva."""
    partes = campo[1:].split("_")
    submissao = next((s for s in folha.respostas if s.questao_id == int(partes[0])), None)
    if submissao is None:
        return None
    return submissao.resposta_do_item(partes[1]) if len(partes) > 1 else (submissao.resposta_aluno or "")


def comparar(sessao, servicos=SERVICOS, revisao: bool = False, sem_texto: bool = False,
             cliente=None) -> tuple[dict, list[dict]]:
    condicoes = list(servicos) + ([f"{s}+revisao" for s in servicos] if revisao else [])
    somas = {c: {"campos": 0, "cer": 0.0, "wer": 0.0, "falhas": 0} for c in condicoes}
    linhas = []
    filtro = [PaginaDigitalizada.situacao == IDENTIFICADA, LeituraPagina.conferida_em.is_not(None)]
    if sem_texto:
        filtro.append(LeituraPagina.conferida_sem_texto.is_(True))
    paginas = sessao.scalars(select(PaginaDigitalizada).join(LeituraPagina).where(*filtro))
    for pagina in paginas:
        folha = pagina.folha
        layout = paginas_do_layout(folha.atividade)
        if not 1 <= (pagina.pagina or 0) <= len(layout) or not layout[pagina.pagina - 1].caixas:
            continue
        pagina_layout = layout[pagina.pagina - 1]
        imagem = cv2.imread(str(caminho(pagina)), cv2.IMREAD_GRAYSCALE)
        if imagem is None:
            continue
        try:
            alinhada = alinhar(imagem, pagina_layout)
        except AlinhamentoFalhou:
            continue
        imagem_ocr = alinhada.ampliada(ocr.ESCALA_OCR)
        for servico in servicos:
            try:
                textos, latencia, _ = ocr.transcrever(imagem_ocr, ocr.ESCALA_OCR, pagina_layout.caixas,
                                                      servico=servico)
            except (ocr.OcrFalhou, ocr.OcrIndisponivel) as erro:
                somas[servico]["falhas"] += 1
                print(f"{servico}, folha {folha.codigo}, página {pagina.pagina}: {erro}", file=sys.stderr)
                continue
            resultados = [(servico, textos)]
            if revisao:
                revisados, _ = _revisar(sessao, imagem_ocr, ocr.ESCALA_OCR, pagina_layout.caixas, textos, cliente, None)
                resultados.append((f"{servico}+revisao", revisados))
            for condicao, textos_condicao in resultados:
                for campo, lido in textos_condicao.items():
                    certo = referencia(folha, campo)
                    if certo is None:
                        continue
                    cer, wer = taxa_de_erro(lido, certo), taxa_de_erro(lido, certo, por_palavra=True)
                    somas[condicao]["campos"] += 1
                    somas[condicao]["cer"] += cer
                    somas[condicao]["wer"] += wer
                    linhas.append({"servico": condicao, "folha": folha.codigo, "pagina": pagina.pagina,
                                   "campo": campo, "cer": round(cer, 4), "wer": round(wer, 4),
                                   "latencia_ms": round(latencia), "lido": lido, "conferido": certo})
    return somas, linhas


def resumo(somas: dict) -> str:
    partes = []
    for servico, s in somas.items():
        if s["campos"]:
            partes.append(f"{servico}: {s['campos']} campos, CER médio {s['cer'] / s['campos']:.1%}, "
                          f"WER médio {s['wer'] / s['campos']:.1%}"
                          + (f", {s['falhas']} páginas com falha" if s["falhas"] else "") + ".")
        else:
            partes.append(f"{servico}: nenhum campo comparado" + (f" ({s['falhas']} falhas)" if s["falhas"] else "") + ".")
    return "\n".join(partes)


def main() -> None:
    from app.database import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", help="grava uma linha por campo e serviço neste arquivo")
    parser.add_argument("--revisao", action="store_true", help="mede também cada serviço com a revisão da IA")
    parser.add_argument("--sem-texto", action="store_true",
                        help="só as páginas conferidas sem o texto lido (referência sem influência)")
    args = parser.parse_args()
    with SessionLocal() as sessao:
        somas, linhas = comparar(sessao, revisao=args.revisao, sem_texto=args.sem_texto)
    if args.sem_texto and not linhas:
        print("Nenhuma página foi conferida sem o texto lido ainda.")
    print(resumo(somas))
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=["servico", "folha", "pagina", "campo", "cer", "wer",
                                                           "latencia_ms", "lido", "conferido"])
            escritor.writeheader()
            escritor.writerows(linhas)
        print(f"{len(linhas)} linhas gravadas em {args.csv}.")


if __name__ == "__main__":
    main()
