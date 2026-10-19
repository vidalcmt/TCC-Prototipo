"""Baixa questões do ENEM pela API comunitária enem.dev e congela uma cópia local.

Por que congelar: a API é mantida pela comunidade e pode mudar ou sair do ar.
A pesquisa precisa saber exatamente quais questões usou, então o script grava
um arquivo JSON em dados/enem/ com a data de acesso, e a coleta usa esse arquivo.

Uso (no seu computador, com internet):
    python -m scripts.importar_enem --ano 2023 --area ciencias-humanas
    python -m scripts.importar_enem --ano 2023 --area ciencias-humanas --importar

Filtro padrão: só questões totalmente em texto, sem imagem no enunciado nem nas
alternativas. Imagem exigiria um modelo multimodal e acrescentaria uma variável
que a pesquisa não quer medir agora. Use --com-imagens para desligar o filtro.

Limite da API: 1 requisição por segundo. O script espera entre as páginas.
"""

import argparse
import json
import time
from datetime import date

import httpx

from app.config import RAIZ

URL_API = "https://api.enem.dev/v1"
AREAS = ["ciencias-humanas", "ciencias-natureza", "linguagens", "matematica"]
PASTA_SAIDA = RAIZ / "dados" / "enem"
TAMANHO_PAGINA = 50
ESPERA_SEGUNDOS = 1.1
MAX_TENTATIVAS_429 = 5


class LimiteDaApiExcedido(RuntimeError):
    pass


def buscar_questoes(ano: int, cliente: httpx.Client, espera: float = ESPERA_SEGUNDOS) -> list[dict]:
    """Percorre todas as páginas da prova do ano, respeitando o limite da API.

    Se a API recusar por excesso de requisições (código 429) mais de
    MAX_TENTATIVAS_429 vezes seguidas, o script para com uma mensagem clara em
    vez de ficar tentando para sempre.
    """
    questoes, offset, recusas = [], 0, 0
    while True:
        resposta = cliente.get(
            f"/exams/{ano}/questions", params={"limit": TAMANHO_PAGINA, "offset": offset}
        )
        if resposta.status_code == 429:
            recusas += 1
            if recusas > MAX_TENTATIVAS_429:
                raise LimiteDaApiExcedido(
                    f"A API recusou {recusas} vezes seguidas. Espere alguns minutos e rode de novo."
                )
            # Retry-After vem em milissegundos, segundo a documentação da API.
            time.sleep(int(resposta.headers.get("Retry-After", "2000")) / 1000 if espera else 0)
            continue
        recusas = 0
        resposta.raise_for_status()
        dados = resposta.json()
        questoes.extend(dados["questions"])
        if not dados["metadata"]["hasMore"]:
            return questoes
        offset += TAMANHO_PAGINA
        time.sleep(espera)


def somente_texto(questao: dict) -> bool:
    if questao.get("files"):
        return False
    if "![" in (questao.get("context") or ""):
        return False
    return all(a.get("text") and not a.get("file") for a in questao["alternatives"])


def filtrar(questoes: list[dict], area: str, exigir_texto: bool = True) -> list[dict]:
    selecionadas = [q for q in questoes if q.get("discipline") == area]
    if exigir_texto:
        selecionadas = [q for q in selecionadas if somente_texto(q)]
    return sorted(selecionadas, key=lambda q: q["index"])


def montar_enunciado(questao: dict) -> str:
    partes = [questao.get("context") or "", questao.get("alternativesIntroduction") or ""]
    return "\n\n".join(p.strip() for p in partes if p and p.strip())


def salvar_copia(questoes: list[dict], ano: int, area: str, exigir_texto: bool) -> str:
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    caminho = PASTA_SAIDA / f"enem_{ano}_{area}.json"
    conteudo = {
        "fonte": f"{URL_API}/exams/{ano}/questions",
        "data_acesso": date.today().isoformat(),
        "filtros": {"ano": ano, "area": area, "somente_texto": exigir_texto},
        "total": len(questoes),
        "questoes": questoes,
    }
    caminho.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(caminho)


def importar_no_banco(questoes: list[dict], sessao) -> int:
    """Grava as questões como objetivas. Ignora as que já foram importadas."""
    from app.models import Alternativa, Questao

    novas = 0
    for q in questoes:
        fonte = f"ENEM {q['year']}, questão {q['index']}"
        if sessao.query(Questao).filter_by(fonte=fonte).first():
            continue
        questao = Questao(
            tipo="objetiva",
            enunciado=montar_enunciado(q),
            area=q.get("discipline"),
            fonte=fonte,
            ano=q["year"],
        )
        questao.alternativas = [
            Alternativa(letra=a["letter"], texto=a["text"], correta=a["letter"] == q["correctAlternative"])
            for a in q["alternatives"]
        ]
        sessao.add(questao)
        novas += 1
    sessao.commit()
    return novas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--area", choices=AREAS, required=True)
    parser.add_argument("--com-imagens", action="store_true", help="não filtra questões com imagem")
    parser.add_argument("--importar", action="store_true", help="grava também no banco do protótipo")
    args = parser.parse_args()

    exigir_texto = not args.com_imagens
    with httpx.Client(base_url=URL_API, timeout=30) as cliente:
        todas = buscar_questoes(args.ano, cliente)
    selecionadas = filtrar(todas, args.area, exigir_texto)
    caminho = salvar_copia(selecionadas, args.ano, args.area, exigir_texto)

    da_area = sum(1 for q in todas if q.get("discipline") == args.area)
    print(f"Prova {args.ano}: {len(todas)} questões no total, {da_area} de {args.area}.")
    print(f"Selecionadas (somente texto={exigir_texto}): {len(selecionadas)}")
    print(f"Cópia congelada em: {caminho}")
    for q in selecionadas:
        print(f"  questão {q['index']:>3}  gabarito {q['correctAlternative']}  {len(montar_enunciado(q))} caracteres")

    if args.importar:
        from app.database import SessionLocal

        with SessionLocal() as sessao:
            print(f"Importadas para o banco: {importar_no_banco(selecionadas, sessao)} novas")


if __name__ == "__main__":
    main()
