"""Números da página de monitoramento: tempo de resposta, erros, serviços externos e servidor."""

import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import RAIZ, config
from app.models import LeituraPagina, MetricaRequisicao, RequisicaoHttp, agora
from app.templates_config import data_local

PERIODOS = {
    "1h": ("Última hora", timedelta(hours=1), timedelta(minutes=5)),
    "24h": ("Últimas 24 horas", timedelta(hours=24), timedelta(hours=1)),
    "7d": ("Últimos 7 dias", timedelta(days=7), timedelta(days=1)),
    "30d": ("Últimos 30 dias", timedelta(days=30), timedelta(days=1)),
}
LENTA_MS = 3000.0
INICIO_DO_PROCESSO = time.time()


def percentil(valores: list[float], p: float) -> float | None:
    """Percentil com interpolação linear (p entre 0 e 100)."""
    if not valores:
        return None
    ordenados = sorted(valores)
    posicao = (len(ordenados) - 1) * p / 100
    baixo = int(posicao)
    alto = min(baixo + 1, len(ordenados) - 1)
    return ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (posicao - baixo)


@dataclass
class Estatisticas:
    total: int = 0
    p50: float | None = None
    p95: float | None = None
    maximo: float | None = None
    erros: int = 0

    @classmethod
    def de(cls, duracoes: list[float], erros: int = 0) -> "Estatisticas":
        return cls(len(duracoes), percentil(duracoes, 50), percentil(duracoes, 95),
                   max(duracoes) if duracoes else None, erros)

    @property
    def taxa_erro(self) -> float | None:
        return self.erros / self.total if self.total else None


@dataclass
class Intervalo:
    inicio: datetime
    rotulo: str
    total: int
    p95: float | None


@dataclass
class Painel:
    periodo: str
    rotulo_periodo: str
    geral: Estatisticas
    lentas: int
    por_rota: list[tuple[str, Estatisticas]]
    intervalos: list[Intervalo]
    mais_lentas: list[RequisicaoHttp]
    erros_recentes: list[RequisicaoHttp]
    modelo: list[tuple[str, Estatisticas]]
    vision: Estatisticas
    leituras_com_falha: int
    servidor: dict = field(default_factory=dict)


def _sem_fuso(momento: datetime) -> datetime:
    """O SQLite devolve as datas sem fuso; compara-se tudo em UTC sem fuso."""
    return momento.astimezone(timezone.utc).replace(tzinfo=None) if momento.tzinfo else momento


def _inicio_do_intervalo(momento: datetime, passo: timedelta) -> datetime:
    segundos = int(passo.total_seconds())
    base = datetime(2000, 1, 1)
    return base + timedelta(seconds=(int((momento - base).total_seconds()) // segundos) * segundos)


def _rotulo(inicio: datetime, passo: timedelta) -> str:
    return data_local(inicio, "%d/%m" if passo >= timedelta(days=1) else "%H:%M")


def montar(sessao: Session, periodo: str) -> Painel:
    if periodo not in PERIODOS:
        periodo = "24h"
    rotulo, duracao, passo = PERIODOS[periodo]
    agora_utc = _sem_fuso(agora())
    desde = agora_utc - duracao

    requisicoes = sessao.scalars(select(RequisicaoHttp).where(RequisicaoHttp.criado_em >= desde)
                                 .order_by(RequisicaoHttp.id)).all()
    duracoes = [r.duracao_ms for r in requisicoes]
    geral = Estatisticas.de(duracoes, sum(1 for r in requisicoes if r.status >= 500))

    rotas: dict[str, list[RequisicaoHttp]] = {}
    for r in requisicoes:
        rotas.setdefault(f"{r.metodo} {r.rota}", []).append(r)
    por_rota = sorted(((nome, Estatisticas.de([r.duracao_ms for r in lista], sum(1 for r in lista if r.status >= 500)))
                       for nome, lista in rotas.items()), key=lambda par: -(par[1].p95 or 0))

    baldes: dict[datetime, list[float]] = {}
    inicio = _inicio_do_intervalo(desde, passo)
    while inicio <= agora_utc:
        baldes[inicio] = []
        inicio += passo
    for r in requisicoes:
        chave = _inicio_do_intervalo(_sem_fuso(r.criado_em), passo)
        baldes.setdefault(chave, []).append(r.duracao_ms)
    intervalos = [Intervalo(chave, _rotulo(chave, passo), len(v), percentil(v, 95))
                  for chave, v in sorted(baldes.items())]

    chamadas = sessao.scalars(select(MetricaRequisicao).where(MetricaRequisicao.criado_em >= desde)).all()
    grupos: dict[str, list[MetricaRequisicao]] = {}
    for c in chamadas:
        grupos.setdefault("Discursivas" if c.tipo_questao == "discursiva" else "Objetivas", []).append(c)
    modelo = [(nome, Estatisticas.de([c.latencia_ms for c in lista if c.sucesso and c.latencia_ms is not None],
                                     sum(1 for c in lista if not c.sucesso)))
              for nome, lista in sorted(grupos.items())]
    for nome, est in modelo:  # o total inclui as falhas
        est.total = len(grupos[nome])

    leituras = sessao.scalars(select(LeituraPagina).where(LeituraPagina.criado_em >= desde)).all()
    vision = Estatisticas.de([l.latencia_ocr_ms for l in leituras if l.latencia_ocr_ms is not None])

    return Painel(
        periodo=periodo, rotulo_periodo=rotulo, geral=geral,
        lentas=sum(1 for d in duracoes if d >= LENTA_MS), por_rota=por_rota, intervalos=intervalos,
        mais_lentas=sorted(requisicoes, key=lambda r: -r.duracao_ms)[:15],
        erros_recentes=[r for r in reversed(requisicoes) if r.status >= 500][:15],
        modelo=modelo, vision=vision, leituras_com_falha=sum(1 for l in leituras if l.situacao == "falha"),
        servidor=servidor(),
    )


# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------

def _meminfo() -> dict[str, int]:
    """Memória do sistema em bytes, lida de /proc/meminfo (só existe no Linux)."""
    try:
        linhas = Path("/proc/meminfo").read_text().splitlines()
    except OSError:
        return {}
    valores = {}
    for linha in linhas:
        nome, _, resto = linha.partition(":")
        partes = resto.split()
        if partes and partes[0].isdigit():
            valores[nome] = int(partes[0]) * 1024
    return valores


def _memoria_do_processo() -> int | None:
    try:
        for linha in Path("/proc/self/status").read_text().splitlines():
            if linha.startswith("VmRSS:"):
                return int(linha.split()[1]) * 1024
    except OSError:
        return None
    return None


def _tamanho_da_pasta(pasta: Path) -> int:
    total = 0
    for raiz, _, arquivos in os.walk(pasta):
        for nome in arquivos:
            try:
                total += (Path(raiz) / nome).stat().st_size
            except OSError:
                pass
    return total


def servidor() -> dict:
    memoria = _meminfo()
    disco = shutil.disk_usage(RAIZ)
    banco = Path(config.database_url.removeprefix("sqlite:///")) if config.database_url.startswith("sqlite:///") else None
    dados = {
        "memoria_total": memoria.get("MemTotal"),
        "memoria_disponivel": memoria.get("MemAvailable"),
        "swap_total": memoria.get("SwapTotal"),
        "swap_livre": memoria.get("SwapFree"),
        "memoria_processo": _memoria_do_processo(),
        "disco_total": disco.total,
        "disco_livre": disco.free,
        "banco": banco.stat().st_size if banco and banco.is_file() else None,
        "arquivos": _tamanho_da_pasta(Path(config.pasta_arquivos)) if Path(config.pasta_arquivos).is_dir() else 0,
        "no_ar_desde": datetime.fromtimestamp(INICIO_DO_PROCESSO, tz=timezone.utc),
    }
    if dados["memoria_total"] and dados["memoria_disponivel"] is not None:
        dados["memoria_uso"] = 1 - dados["memoria_disponivel"] / dados["memoria_total"]
    dados["disco_uso"] = 1 - disco.free / disco.total if disco.total else None
    return dados
