"""Cópia de segurança do banco, usada todo dia no servidor."""

import gzip
import os
import sqlite3
from datetime import datetime

import pytest

from scripts.copia_banco import apagar_antigas, caminho_do_banco, copiar


def test_copia_compactada_e_legivel(tmp_path):
    banco = tmp_path / "tcc.db"
    with sqlite3.connect(banco) as c:
        c.execute("create table questao (id integer primary key, enunciado text)")
        c.executemany("insert into questao (enunciado) values (?)", [("A",), ("B",)])
    copia = copiar(banco, tmp_path / "copias", agora=datetime(2026, 10, 27, 3, 30))
    assert copia.name == "tcc-20261027-0330.db.gz"
    assert not (tmp_path / "copias" / "tcc-20261027-0330.db").exists()  # o temporário é apagado

    restaurado = tmp_path / "restaurado.db"
    restaurado.write_bytes(gzip.decompress(copia.read_bytes()))
    with sqlite3.connect(restaurado) as c:
        assert c.execute("select count(*) from questao").fetchone()[0] == 2


def test_apaga_so_as_copias_antigas(tmp_path):
    agora = 1_800_000_000
    velha, nova, outro = tmp_path / "tcc-velha.db.gz", tmp_path / "tcc-nova.db.gz", tmp_path / "anotacao.txt"
    for arquivo in (velha, nova, outro):
        arquivo.write_text("x")
    os.utime(velha, (agora - 31 * 86400, agora - 31 * 86400))
    os.utime(nova, (agora - 29 * 86400, agora - 29 * 86400))
    os.utime(outro, (agora - 90 * 86400, agora - 90 * 86400))
    assert apagar_antigas(tmp_path, dias=30, agora=agora) == [velha]
    assert nova.exists() and outro.exists()


def test_so_aceita_sqlite():
    with pytest.raises(SystemExit):
        caminho_do_banco("postgresql://servidor/banco")
