"""Gerenciamento de configurações da aplicação via variáveis de ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Carrega o arquivo .env a partir da raiz do projeto
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()


@dataclass(frozen=True)
class DatabaseConfig:
    """Configurações de conexão ao MySQL."""

    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "3306"))
    user: str = os.getenv("DB_USER", "root")
    password: str = os.getenv("DB_PASSWORD", "")
    database: str = os.getenv("DB_NAME", "expense_control")
    charset: str = os.getenv("DB_CHARSET", "utf8mb4")
    connect_timeout: int = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))


@dataclass(frozen=True)
class AppConfig:
    """Configurações gerais da aplicação."""

    env: str = os.getenv("APP_ENV", "development")
    timezone: str = os.getenv("APP_TIMEZONE", "America/Sao_Paulo")
    db: DatabaseConfig = DatabaseConfig()


# Instância global de configuração
config = AppConfig()
