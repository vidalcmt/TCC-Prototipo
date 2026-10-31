"""Quem está usando o sistema: sessão, permissões e proteção contra abuso.

A sessão é um cookie assinado com SECRET_KEY: o navegador guarda o número do
usuário, mas não consegue alterá-lo sem invalidar a assinatura. Junto vai uma
marca derivada da senha atual; quando a senha muda, as sessões antigas deixam
de valer.

Todas as rotas, exceto as públicas (entrar, arquivos estáticos e /saude),
dependem de exigir_login. Essa dependência é declarada uma vez, ao incluir os
roteadores em app/main.py, e um teste percorre todas as rotas para garantir
que nenhuma ficou sem proteção.
"""

import time
from collections import defaultdict
from datetime import datetime, time as hora
from zoneinfo import ZoneInfo

from fastapi import Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import FUSO, config
from app.database import obter_sessao
from app.models import Correcao, MetricaRequisicao, RevisaoProfessor, Usuario


class NaoAutenticado(Exception):
    """Não há sessão válida: o navegador é levado para a página de entrada."""


class PrecisaTrocarSenha(Exception):
    """Senha provisória: o usuário só pode trocar a senha ou sair."""


class SemPermissao(Exception):
    """Página só para administradores."""


class LimiteDiarioAtingido(Exception):
    """O usuário já fez o número máximo de chamadas ao modelo hoje."""


ROTAS_LIVRES_COM_SENHA_PROVISORIA = {"/trocar-senha", "/sair"}


def marca_da_senha(usuario: Usuario) -> str:
    return usuario.senha_resumo[-16:]


def iniciar_sessao(request: Request, usuario: Usuario) -> None:
    request.session.clear()  # evita reaproveitar uma sessão anterior
    request.session["usuario_id"] = usuario.id
    request.session["marca"] = marca_da_senha(usuario)


def encerrar_sessao(request: Request) -> None:
    request.session.clear()


def usuario_da_sessao(request: Request, sessao: Session) -> Usuario | None:
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return None
    usuario = sessao.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo or request.session.get("marca") != marca_da_senha(usuario):
        request.session.clear()
        return None
    return usuario


def correcoes_pendentes(sessao: Session) -> int:
    """Correções discursivas com nota sugerida que ainda esperam a decisão de alguém."""
    return sessao.scalar(
        select(func.count(Correcao.id))
        .outerjoin(RevisaoProfessor, RevisaoProfessor.correcao_id == Correcao.id)
        .where(Correcao.nota_sugerida.is_not(None), RevisaoProfessor.id.is_(None))
    ) or 0


def exigir_login(request: Request, sessao: Session = Depends(obter_sessao)) -> Usuario:
    usuario = usuario_da_sessao(request, sessao)
    if usuario is None:
        raise NaoAutenticado()
    if usuario.precisa_trocar_senha and request.url.path not in ROTAS_LIVRES_COM_SENHA_PROVISORIA:
        raise PrecisaTrocarSenha()
    # Disponíveis para todos os modelos HTML pela variável request
    request.state.usuario = usuario
    request.state.pendentes = correcoes_pendentes(sessao)
    return usuario


def exigir_admin(usuario: Usuario = Depends(exigir_login)) -> Usuario:
    if not usuario.eh_admin:
        raise SemPermissao()
    return usuario


# ---------------------------------------------------------------------------
# Limite diário de chamadas ao modelo
# ---------------------------------------------------------------------------

def inicio_do_dia_utc() -> datetime:
    """Meia-noite de hoje no horário de Brasília, convertida para UTC sem fuso.

    O SQLite guarda as datas sem fuso, em UTC; por isso a comparação é feita
    com uma data também sem fuso.
    """
    fuso = ZoneInfo(FUSO)
    meia_noite = datetime.combine(datetime.now(fuso).date(), hora.min, tzinfo=fuso)
    return meia_noite.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def chamadas_hoje(sessao: Session, usuario_id: int) -> int:
    return sessao.scalar(
        select(func.count(MetricaRequisicao.id)).where(
            MetricaRequisicao.usuario_id == usuario_id,
            MetricaRequisicao.criado_em >= inicio_do_dia_utc(),
        )
    ) or 0


def verificar_limite_diario(sessao: Session, usuario: Usuario) -> None:
    if chamadas_hoje(sessao, usuario.id) >= config.limite_chamadas_dia:
        raise LimiteDiarioAtingido()


# ---------------------------------------------------------------------------
# Bloqueio após tentativas erradas de senha
# ---------------------------------------------------------------------------

MAX_TENTATIVAS = 5
JANELA_SEGUNDOS = 10 * 60


class ControleDeTentativas:
    """Guarda, em memória, as tentativas erradas por e-mail.

    Depois de MAX_TENTATIVAS erros em JANELA_SEGUNDOS, novas tentativas para
    aquele e-mail são recusadas até a janela passar. Fica em memória porque o
    sistema roda em um único processo; reiniciar o servidor zera a contagem.
    """

    def __init__(self, relogio=time.monotonic, maximo: int = MAX_TENTATIVAS):
        self._erros: dict[str, list[float]] = defaultdict(list)
        self._relogio = relogio
        self._maximo = maximo

    def _recentes(self, chave: str) -> list[float]:
        limite = self._relogio() - JANELA_SEGUNDOS
        self._erros[chave] = [t for t in self._erros[chave] if t > limite]
        return self._erros[chave]

    def bloqueado(self, chave: str) -> bool:
        return len(self._recentes(chave)) >= self._maximo

    def registrar_erro(self, chave: str) -> None:
        self._recentes(chave).append(self._relogio())

    def limpar(self, chave: str) -> None:
        self._erros.pop(chave, None)


tentativas = ControleDeTentativas()
