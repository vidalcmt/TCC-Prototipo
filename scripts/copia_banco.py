"""Cópia de segurança do banco SQLite, para rodar todo dia no servidor.

Uso:
    python -m scripts.copia_banco --destino /var/backups/devolutiva --dias 30

Usa a função de cópia do próprio SQLite, que gera um arquivo consistente
mesmo com o sistema no ar, compacta com gzip e apaga as cópias mais antigas
que o número de dias informado. Com --bucket, envia a cópia também para um
bucket do Cloud Storage (exige a ferramenta gsutil e permissão de escrita).
"""

import argparse
from contextlib import closing
import gzip
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import FUSO, config

PREFIXO = "tcc-"


def caminho_do_banco(url: str) -> Path:
    if not url.startswith("sqlite:///"):
        raise SystemExit("A cópia só funciona com banco SQLite.")
    return Path(url.removeprefix("sqlite:///"))


def copiar(origem: Path, destino: Path, agora: datetime | None = None) -> Path:
    """Copia o banco para destino/tcc-AAAAMMDD-HHMM.db.gz, no horário de Brasília, e devolve o caminho."""
    if not origem.exists():
        raise SystemExit(f"Banco não encontrado: {origem}")
    destino.mkdir(parents=True, exist_ok=True)
    nome = f"{PREFIXO}{(agora or datetime.now(ZoneInfo(FUSO))).strftime('%Y%m%d-%H%M')}.db"
    temporario = destino / nome
    # closing: o "with" do sqlite3 só confirma a transação; aqui a conexão precisa ser fechada.
    with closing(sqlite3.connect(origem)) as fonte, closing(sqlite3.connect(temporario)) as alvo:
        fonte.backup(alvo)
    final = destino / (nome + ".gz")
    with open(temporario, "rb") as entrada, gzip.open(final, "wb") as saida:
        shutil.copyfileobj(entrada, saida)
    temporario.unlink()
    return final


def apagar_antigas(destino: Path, dias: int, agora: float | None = None) -> list[Path]:
    limite = (agora or time.time()) - dias * 86400
    apagadas = []
    for arquivo in destino.glob(f"{PREFIXO}*.db.gz"):
        if arquivo.stat().st_mtime < limite:
            arquivo.unlink()
            apagadas.append(arquivo)
    return apagadas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--destino", required=True, type=Path)
    parser.add_argument("--dias", type=int, default=30, help="por quantos dias guardar as cópias (padrão 30)")
    parser.add_argument("--bucket", default="", help="opcional: gs://nome-do-bucket/pasta")
    args = parser.parse_args()

    copia = copiar(caminho_do_banco(config.database_url), args.destino)
    print(f"Cópia gravada: {copia}")
    for arquivo in apagar_antigas(args.destino, args.dias):
        print(f"Cópia antiga apagada: {arquivo}")
    if args.bucket:
        subprocess.run(["gsutil", "-q", "cp", str(copia), args.bucket.rstrip("/") + "/"], check=True)
        print(f"Enviada para {args.bucket}")


if __name__ == "__main__":
    main()
