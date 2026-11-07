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

O CSV tem uma linha por campo e não contém nenhum dado de aluno além do
código da folha.
"""

import argparse
import csv
import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LeituraPagina, Submissao
from app.resultados.servico import MARCACAO_MULTIPLA


def distancia(a: list | str, b: list | str) -> int:
    """Distância de edição (Levenshtein): inserções, remoções e trocas."""
    anterior = list(range(len(b) + 1))
    for i, x in enumerate(a, start=1):
        atual = [i]
        for j, y in enumerate(b, start=1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (x != y)))
        anterior = atual
    return anterior[-1]


def _normalizar(texto: str) -> str:
    return " ".join((texto or "").split())


def taxa_de_erro(lido: str, conferido: str, por_palavra: bool = False) -> float:
    a, b = _normalizar(lido), _normalizar(conferido)
    if por_palavra:
        a, b = a.split(), b.split()
    if not b:
        return 0.0 if not a else 1.0
    return distancia(a, b) / len(b)


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
    linhas: list[dict] = field(default_factory=list)

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
        return "\n".join(partes) or "Nenhuma leitura conferida ainda."


def _marcacao_final(submissao: Submissao) -> str:
    if not submissao.alternativa_escolhida:
        return "branco"
    return "multipla" if submissao.alternativa_escolhida == MARCACAO_MULTIPLA else submissao.alternativa_escolhida


def medir(sessao: Session) -> Medida:
    medida = Medida()
    leituras = sessao.scalars(select(LeituraPagina).where(LeituraPagina.conferida_em.is_not(None),
                                                         LeituraPagina.situacao == "lida"))
    for leitura in leituras:
        folha = leitura.pagina_digitalizada.folha
        if folha is None:
            continue
        respostas = {s.questao_id: s for s in folha.respostas}
        resultado = json.loads(leitura.resultado_json)
        for qid, lido in resultado.get("objetivas", {}).items():
            submissao = respostas.get(int(qid))
            if submissao is None:
                continue
            final = _marcacao_final(submissao)
            certo = lido["marcada"] == final
            medida.objetivas += 1
            medida.acertos += certo
            medida.duvidosas += bool(lido["duvida"])
            if not lido["duvida"]:
                medida.sem_duvida += 1
                medida.acertos_sem_duvida += certo
            medida.linhas.append({"folha": folha.codigo, "campo": f"q{qid}", "tipo": "objetiva",
                                  "lido": lido["marcada"], "conferido": final, "duvida": lido["duvida"],
                                  "acerto": certo, "cer": "", "wer": ""})
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
            medida.linhas.append({"folha": folha.codigo, "campo": campo, "tipo": "discursiva", "lido": texto,
                                  "conferido": final, "duvida": "", "acerto": "", "cer": round(cer, 4),
                                  "wer": round(wer, 4)})
    return medida


def main() -> None:
    from app.database import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", help="grava uma linha por campo neste arquivo")
    args = parser.parse_args()
    with SessionLocal() as sessao:
        medida = medir(sessao)
    print(medida.resumo())
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=["folha", "campo", "tipo", "lido", "conferido", "duvida",
                                                           "acerto", "cer", "wer"])
            escritor.writeheader()
            escritor.writerows(medida.linhas)
        print(f"{len(medida.linhas)} linhas gravadas em {args.csv}.")


if __name__ == "__main__":
    main()
