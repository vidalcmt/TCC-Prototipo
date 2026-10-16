"""Configuração lida do arquivo .env (ou de variáveis de ambiente)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parent.parent


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_file=RAIZ / ".env", extra="ignore")

    openai_api_key: str = ""
    modelo: str = "gpt-6.1-sol"
    database_url: str = f"sqlite:///{RAIZ / 'tcc.db'}"


config = Configuracao()
