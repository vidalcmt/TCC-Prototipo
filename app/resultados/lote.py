"""Correção em lote das discursivas de uma atividade, fora da requisição.

Uma turma de 40 alunos com duas discursivas são 80 chamadas ao modelo, o que
levaria vários minutos: a página não pode esperar por isso. A correção roda
numa linha de execução separada, e a página do painel mostra o andamento.

O andamento fica em memória, o que basta porque o servidor roda com um único
processo (`--workers 1`). Se o servidor reiniciar no meio, o lote para; as
respostas que faltaram continuam pendentes e basta pedir de novo.
"""

import threading
from dataclasses import dataclass

from openai import OpenAI
from sqlalchemy.orm import Session, sessionmaker

from app.contas.sessao import chamadas_hoje
from app.config import config
from app.models import Atividade, Submissao
from app.resultados.servico import corrigir_discursiva, discursivas_a_corrigir


@dataclass
class Andamento:
    total: int
    feitas: int = 0
    falhas: int = 0
    em_andamento: bool = True
    mensagem: str = ""


_andamentos: dict[int, Andamento] = {}
_linhas: dict[int, threading.Thread] = {}
_trava = threading.Lock()


def andamento(atividade_id: int) -> Andamento | None:
    return _andamentos.get(atividade_id)


def iniciar(fabrica: sessionmaker, atividade_id: int, usuario_id: int, cliente: OpenAI | None) -> Andamento | None:
    """Começa o lote, ou devolve None se já há um em andamento para a atividade."""
    with _trava:
        atual = _andamentos.get(atividade_id)
        if atual is not None and atual.em_andamento:
            return None
        with fabrica() as sessao:
            ids = [s.id for s in discursivas_a_corrigir(sessao, sessao.get(Atividade, atividade_id))]
        estado = Andamento(total=len(ids))
        _andamentos[atividade_id] = estado
        linha = threading.Thread(target=_executar, args=(fabrica, estado, ids, usuario_id, cliente), daemon=True)
        _linhas[atividade_id] = linha
        linha.start()
        return estado


def aguardar(atividade_id: int, segundos: float = 30) -> None:
    """Usada nos testes, para esperar o fim do lote."""
    linha = _linhas.get(atividade_id)
    if linha is not None:
        linha.join(segundos)


def _executar(fabrica: sessionmaker, estado: Andamento, ids: list[int], usuario_id: int,
              cliente: OpenAI | None) -> None:
    try:
        with fabrica() as sessao:
            for submissao_id in ids:
                if chamadas_hoje(sessao, usuario_id) >= config.limite_chamadas_dia:
                    estado.mensagem = ("Limite diário de chamadas atingido. As respostas que faltaram "
                                       "continuam pendentes e podem ser corrigidas amanhã.")
                    break
                _corrigir_uma(sessao, estado, sessao.get(Submissao, submissao_id), usuario_id, cliente)
    except Exception as erro:  # o lote não pode derrubar o servidor
        estado.mensagem = f"O lote parou por um erro inesperado: {erro}"
    finally:
        estado.em_andamento = False


def _corrigir_uma(sessao: Session, estado: Andamento, submissao: Submissao, usuario_id: int,
                  cliente: OpenAI | None) -> None:
    try:
        sucesso = corrigir_discursiva(sessao, submissao, cliente, usuario_id).sucesso
    except Exception:
        sessao.rollback()
        sucesso = False
    if sucesso:
        estado.feitas += 1
    else:
        estado.falhas += 1
