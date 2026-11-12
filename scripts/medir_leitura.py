"""Mede a taxa de acerto da leitura automática das folhas digitalizadas.

Uso:
    python -m scripts.medir_leitura
    python -m scripts.medir_leitura --csv leitura.csv

Compara o que foi lido (bolinhas e escrita) com as respostas que o professor
conferiu e salvou. Só entram as páginas cuja leitura já foi conferida.

- Objetivas: proporção de questões em que a leitura acertou a marcação
  (letra, em branco ou mais de uma), no total e entre as não marcadas como
  duvidosas.
- Discursivas: taxa de erro de caracteres (CER) e de palavras (WER), a
  distância de edição entre o texto lido e o conferido dividida pelo tamanho
  do conferido. 0 é transcrição perfeita.
- Alinhamento: quantas páginas foram alinhadas por cada método (marcas dos
  cantos, QR code e caixas, ou aproximado pelas bordas), o erro médio medido
  nas caixas, em milímetros, e os resultados acima separados por método. É a
  comparação entre folhas com e sem as marcas dos cantos.
- Referência sem influência: as folhas conferidas sem o texto lido, em que
  o professor digitou a escrita a partir da imagem, são medidas também à
  parte. Nas outras, a referência foi corrigida sobre o texto lido e tende a
  ficar parecida com ele, o que deixa a taxa de erro otimista.
- Revisão da IA: nos campos em que a revisão foi aplicada, o CER do texto do
  OCR sozinho e o do texto revisado, contra o mesmo texto conferido, e em
  quantos campos a revisão melhorou ou piorou. Piorar quer dizer que o
  professor voltou atrás numa troca, quase sempre um erro do aluno que a IA
  corrigiu ou uma palavra que ela adivinhou.

O CSV tem uma linha por campo e não contém nenhum dado de aluno além do
código da folha.
"""

import argparse
import csv
import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.leitura.medida import distancia, taxa_de_erro  # noqa: F401  (usadas também pelos testes)
from app.models import LeituraPagina, Submissao
from app.resultados.servico import MARCACAO_MULTIPLA


@dataclass
class Medida:
    objetivas: int = 0
    acertos: int = 0
    duvidosas: int = 0
    acertos_sem_duvida: int = 0
    sem_duvida: int = 0
    textos: int = 0
    soma_cer: float = 0.0
    soma_wer: float = 0.0
    revisados: int = 0
    soma_cer_ocr: float = 0.0
    soma_cer_revisado: float = 0.0
    melhorou: int = 0
    piorou: int = 0
    linhas: list[dict] = field(default_factory=list)
    # por método de alinhamento: páginas, erros em mm, objetivas, acertos, textos, soma do CER
    metodos: dict = field(default_factory=dict)

    def _metodo(self, nome: str) -> dict:
        return self.metodos.setdefault(nome, {"paginas": 0, "erros": [], "objetivas": 0, "acertos": 0,
                                              "textos": 0, "soma_cer": 0.0})

    def resumo(self) -> str:
        partes = []
        if self.objetivas:
            partes.append(f"Objetivas: {self.acertos} de {self.objetivas} lidas corretamente "
                          f"({self.acertos / self.objetivas:.1%}); {self.duvidosas} marcadas como duvidosas.")
            if self.sem_duvida:
                partes.append(f"Entre as não duvidosas: {self.acertos_sem_duvida} de {self.sem_duvida} "
                              f"({self.acertos_sem_duvida / self.sem_duvida:.1%}).")
        if self.textos:
            partes.append(f"Discursivas: {self.textos} campos; CER médio {self.soma_cer / self.textos:.1%}, "
                          f"WER médio {self.soma_wer / self.textos:.1%}.")
        if self.revisados:
            partes.append(f"Revisão da IA: {self.revisados} campo(s) revisado(s); CER do OCR sozinho "
                          f"{self.soma_cer_ocr / self.revisados:.1%}, com a revisão "
                          f"{self.soma_cer_revisado / self.revisados:.1%}; melhorou {self.melhorou}, "
                          f"piorou {self.piorou}.")
        for nome, m in sorted(self.metodos.items()):
            linha = f"Alinhamento {nome}: {m['paginas']} páginas"
            if m["erros"]:
                linha += f", erro médio nas caixas {sum(m['erros']) / len(m['erros']):.2f} mm"
            if m["objetivas"]:
                linha += f", objetivas {m['acertos'] / m['objetivas']:.1%}"
            if m["textos"]:
                linha += f", CER {m['soma_cer'] / m['textos']:.1%}"
            partes.append(linha + ".")
        return "\n".join(partes) or "Nenhuma leitura conferida ainda."


def _marcacao_final(submissao: Submissao) -> str:
    if not submissao.alternativa_escolhida:
        return "branco"
    return "multipla" if submissao.alternativa_escolhida == MARCACAO_MULTIPLA else submissao.alternativa_escolhida


def medir(sessao: Session, sem_texto: bool = False) -> Medida:
    """Com sem_texto, só as leituras conferidas com os campos da escrita vazios."""
    medida = Medida()
    filtro = [LeituraPagina.conferida_em.is_not(None), LeituraPagina.situacao == "lida"]
    if sem_texto:
        filtro.append(LeituraPagina.conferida_sem_texto.is_(True))
    leituras = sessao.scalars(select(LeituraPagina).where(*filtro))
    for leitura in leituras:
        folha = leitura.pagina_digitalizada.folha
        if folha is None:
            continue
        respostas = {s.questao_id: s for s in folha.respostas}
        resultado = json.loads(leitura.resultado_json)
        alinhamento = resultado.get("alinhamento") or {"metodo": "marcas"}  # leituras anteriores à medida
        metodo = medida._metodo(alinhamento["metodo"])
        metodo["paginas"] += 1
        if alinhamento.get("erro_mm") is not None:
            metodo["erros"].append(alinhamento["erro_mm"])
        for qid, lido in resultado.get("objetivas", {}).items():
            submissao = respostas.get(int(qid))
            if submissao is None:
                continue
            final = _marcacao_final(submissao)
            certo = lido["marcada"] == final
            medida.objetivas += 1
            medida.acertos += certo
            metodo["objetivas"] += 1
            metodo["acertos"] += certo
            medida.duvidosas += bool(lido["duvida"])
            if not lido["duvida"]:
                medida.sem_duvida += 1
                medida.acertos_sem_duvida += certo
            medida.linhas.append({"folha": folha.codigo, "alinhamento": alinhamento["metodo"], "campo": f"q{qid}", "tipo": "objetiva",
                                  "lido": lido["marcada"], "conferido": final, "duvida": lido["duvida"],
                                  "acerto": certo, "cer": "", "wer": "", "lido_ocr": "", "cer_ocr": ""})
        textos_ocr, revisoes = resultado.get("textos_ocr", {}), resultado.get("revisoes", {})
        for campo, texto in resultado.get("textos", {}).items():
            partes = campo[1:].split("_")
            submissao = respostas.get(int(partes[0]))
            if submissao is None:
                continue
            final = submissao.resposta_do_item(partes[1]) if len(partes) > 1 else (submissao.resposta_aluno or "")
            cer, wer = taxa_de_erro(texto, final), taxa_de_erro(texto, final, por_palavra=True)
            medida.textos += 1
            medida.soma_cer += cer
            medida.soma_wer += wer
            metodo["textos"] += 1
            metodo["soma_cer"] += cer
            lido_ocr, cer_ocr = "", ""
            revisao = revisoes.get(campo)
            if revisao is not None and not revisao.get("descartada") and campo in textos_ocr:
                lido_ocr = textos_ocr[campo]
                cer_ocr = taxa_de_erro(lido_ocr, final)
                medida.revisados += 1
                medida.soma_cer_ocr += cer_ocr
                medida.soma_cer_revisado += cer
                medida.melhorou += cer < cer_ocr
                medida.piorou += cer > cer_ocr
                cer_ocr = round(cer_ocr, 4)
            medida.linhas.append({"folha": folha.codigo, "alinhamento": alinhamento["metodo"], "campo": campo, "tipo": "discursiva", "lido": texto,
                                  "conferido": final, "duvida": "", "acerto": "", "cer": round(cer, 4),
                                  "wer": round(wer, 4), "lido_ocr": lido_ocr, "cer_ocr": cer_ocr})
    return medida


def main() -> None:
    from app.database import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", help="grava uma linha por campo neste arquivo")
    args = parser.parse_args()
    from app.leitura.avaliacao import NOTAS, VEREDITOS, resumo as resumo_avaliacoes

    with SessionLocal() as sessao:
        medida = medir(sessao)
        sem_texto = medir(sessao, sem_texto=True)
        total, grupos = resumo_avaliacoes(sessao)
    print(medida.resumo())
    if total.total or total.trocas_avaliadas:
        print("\nAvaliação da leitura pelo administrador:")
        for g in grupos + [total]:
            notas = ", ".join(f"{rotulo} {g.notas[chave]} ({g.fracao(chave):.0%})" for chave, (rotulo, _) in NOTAS.items())
            trocas = ", ".join(f"{rotulo} {g.vereditos[chave]} ({g.fracao_trocas(chave):.0%})"
                               for chave, (rotulo, _) in VEREDITOS.items())
            print(f"{g.nome}: {g.total} respostas com nota ({notas}); {g.trocas_avaliadas} de {g.trocas} trocas "
                  f"avaliadas ({trocas}).")
    if sem_texto.textos:
        print("\nSó as folhas conferidas sem o texto lido (referência sem a influência da leitura):")
        print(sem_texto.resumo())
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=["folha", "alinhamento", "campo", "tipo", "lido", "conferido", "duvida",
                                                           "acerto", "cer", "wer", "lido_ocr", "cer_ocr"])
            escritor.writeheader()
            escritor.writerows(medida.linhas)
        print(f"{len(medida.linhas)} linhas gravadas em {args.csv}.")


if __name__ == "__main__":
    main()
