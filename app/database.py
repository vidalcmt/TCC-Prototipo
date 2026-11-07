"""Conexão com o banco SQLite e fábrica de sessões."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import config


class Base(DeclarativeBase):
    pass


engine = create_engine(config.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def obter_sessao() -> Iterator[Session]:
    """Dependência do FastAPI: abre uma sessão por requisição e fecha ao final."""
    sessao = SessionLocal()
    try:
        yield sessao
    finally:
        sessao.close()


def obter_fabrica_sessao() -> sessionmaker:
    """Dependência do FastAPI para trabalhos que continuam depois da resposta,
    como a correção em lote, e precisam abrir as próprias sessões."""
    return SessionLocal
