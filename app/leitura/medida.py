"""Distância de edição e taxas de erro de transcrição (CER e WER).

Ficam aqui, e não só no script de medida, porque a revisão da transcrição
também usa a taxa de erro para recusar uma revisão que muda demais o texto.
"""


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
