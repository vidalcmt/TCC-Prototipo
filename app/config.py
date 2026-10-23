"""Configuração lida do arquivo .env (ou de variáveis de ambiente)."""

import secrets
import warnings
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parent.parent
FUSO = "America/Sao_Paulo"


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_file=RAIZ / ".env", extra="ignore")

    openai_api_key: str = ""
    modelo: str = "gpt-6.1-sol"
    database_url: str = f"sqlite:///{RAIZ / 'tcc.db'}"

    nome_sistema: str = "Devolutiva"

    # Chave que assina o cookie de sessão. Em produção, defina no .env um valor
    # longo e aleatório; sem ela, uma chave temporária é gerada a cada início e
    # todos precisam entrar de novo quando o servidor reinicia.
    secret_key: str = ""
    # Verdadeiro em produção (HTTPS): o navegador só envia o cookie por conexão segura.
    cookie_seguro: bool = False
    duracao_sessao_horas: int = 12

    # Proteção de custo: chamadas ao modelo por usuário por dia (horário de Brasília).
    limite_chamadas_dia: int = 60


config = Configuracao()

if not config.secret_key:
    config.secret_key = secrets.token_urlsafe(48)
    warnings.warn(
        "SECRET_KEY não definida no .env: usando uma chave temporária. "
        "As sessões serão perdidas quando o servidor reiniciar.",
        stacklevel=1,
    )
