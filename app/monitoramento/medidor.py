"""Mede o tempo de resposta de cada requisição ao site.

É um middleware ASGI: envolve a aplicação inteira, marca o tempo na entrada,
anota o status da resposta e, ao fim, grava uma linha em `requisicao_http`.
Arquivos estáticos e a rota /saude (consultada a cada poucos minutos pela
verificação de disponibilidade do Google Cloud) ficam de fora.

O endereço real nunca é gravado: a rota é a declarada no código, com os
parâmetros no lugar dos valores (`/r/{codigo}`, `/atividades/{atividade_id}`).
Requisições lentas e erros do servidor também vão para o log da aplicação, que
o Google Cloud Logging pode coletar (guia de publicação, seção 7).
"""

import logging
import time
from datetime import timedelta

import anyio
from sqlalchemy import delete
from starlette.routing import Match

from app.database import obter_fabrica_sessao
from app.models import RequisicaoHttp, agora

log = logging.getLogger("devolutiva.monitoramento")

IGNORADAS = ("/static/", "/saude")
LENTA_MS = 3000.0
RETENCAO_DIAS = 30
LIMPAR_A_CADA = 500  # gravações


class MedidorDeRequisicoes:
    def __init__(self, app):
        self.app = app
        self._gravacoes = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"].startswith(IGNORADAS):
            await self.app(scope, receive, send)
            return
        inicio = time.perf_counter()
        resposta = {"status": 500}

        async def enviar(mensagem):
            if mensagem["type"] == "http.response.start":
                resposta["status"] = mensagem["status"]
            await send(mensagem)

        try:
            await self.app(scope, receive, enviar)
        finally:
            duracao = (time.perf_counter() - inicio) * 1000
            rota = rota_declarada(scope)
            if resposta["status"] >= 500 or duracao >= LENTA_MS:
                log.warning("requisicao %s metodo=%s rota=%s status=%s duracao_ms=%.0f",
                            "com_erro" if resposta["status"] >= 500 else "lenta",
                            scope.get("method"), rota, resposta["status"], duracao)
            try:
                await anyio.to_thread.run_sync(self._gravar, scope, rota, resposta["status"], duracao)
            except Exception:  # medir nunca pode derrubar a requisição
                log.exception("Falha ao gravar a medida da requisição")

    def _gravar(self, scope, rota: str, status: int, duracao: float) -> None:
        app = scope.get("app")
        fabrica = (getattr(app, "dependency_overrides", {}) or {}).get(obter_fabrica_sessao, obter_fabrica_sessao)()
        with fabrica() as sessao:
            sessao.add(RequisicaoHttp(metodo=scope.get("method", "")[:10], rota=rota[:200], status=status,
                                      duracao_ms=round(duracao, 1)))
            self._gravacoes += 1
            if self._gravacoes % LIMPAR_A_CADA == 1:
                sessao.execute(delete(RequisicaoHttp).where(
                    RequisicaoHttp.criado_em < agora() - timedelta(days=RETENCAO_DIAS)))
            sessao.commit()


def _rotas(itens, prefixo: str = ""):
    """As rotas da aplicação, uma a uma, com o prefixo de cada grupo.

    Versões recentes do FastAPI guardam os grupos de rotas incluídos com
    `include_router` dentro de um envoltório, sem copiar as rotas para a lista
    principal; versões anteriores copiavam. Os dois casos são aceitos.
    """
    for item in itens:
        original = getattr(item, "original_router", None)
        if original is not None:
            contexto = getattr(item, "include_context", None)
            yield from _rotas(original.routes, prefixo + (getattr(contexto, "prefix", "") or ""))
        else:
            yield prefixo, item


_cache: dict[int, list] = {}


def rota_declarada(scope) -> str:
    """O caminho da rota que atende a requisição, como está no código."""
    app = scope.get("app")
    if app is None:
        return "(sem rota)"
    rotas = _cache.get(id(app))
    if rotas is None:
        rotas = _cache[id(app)] = list(_rotas(getattr(app, "routes", [])))
    caminho = scope.get("path", "")
    for prefixo, rota in rotas:
        if prefixo and not caminho.startswith(prefixo):
            continue
        alvo = dict(scope, path=caminho[len(prefixo):] or "/") if prefixo else scope
        correspondencia, _ = rota.matches(alvo)
        if correspondencia == Match.FULL:
            return prefixo + (getattr(rota, "path", "") or "") or "(sem rota)"
    return "(sem rota)"
