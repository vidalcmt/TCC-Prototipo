"""Leitura em lote das páginas de uma atividade, fora da requisição.

Mesmo funcionamento da correção em lote (app/resultados/lote.py): uma linha
de execução por atividade e o andamento em memória.
"""

import threading
from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from app.leitura.servico import FALHA, ler_pagina, paginas_para_ler
from app.models import Atividade, PaginaDigitalizada


@dataclass
class Andamento:
    total: int
    feitas: int = 0
    falhas: int = 0
    em_andamento: bool = True
    mensagem: str = ""


_andamentos: dict[int, Andamento] = {}
_trava = threading.Lock()


def andamento(atividade_id: int) -> Andamento | None:
    return _andamentos.get(atividade_id)


def iniciar(fabrica: sessionmaker, atividade_id: int, usuario_id: int) -> Andamento | None:
    with _trava:
        atual = _andamentos.get(atividade_id)
        if atual is not None and atual.em_andamento:
            return None
        with fabrica() as sessao:
            ids = [p.id for p in paginas_para_ler(sessao, sessao.get(Atividade, atividade_id))]
        estado = Andamento(total=len(ids))
        _andamentos[atividade_id] = estado
        threading.Thread(target=_executar, args=(fabrica, estado, ids, usuario_id), daemon=True).start()
        return estado


def _executar(fabrica: sessionmaker, estado: Andamento, ids: list[int], usuario_id: int) -> None:
    try:
        with fabrica() as sessao:
            for pagina_id in ids:
                try:
                    leitura = ler_pagina(sessao, sessao.get(PaginaDigitalizada, pagina_id), usuario_id)
                    falhou = leitura.situacao == FALHA
                except Exception:
                    sessao.rollback()
                    falhou = True
                if falhou:
                    estado.falhas += 1
                else:
                    estado.feitas += 1
    except Exception as erro:
        estado.mensagem = f"A leitura parou por um erro inesperado: {erro}"
    finally:
        estado.em_andamento = False
