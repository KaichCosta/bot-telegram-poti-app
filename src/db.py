"""Camada de infraestrutura de banco de dados MySQL usando PyMySQL."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator, Optional

import pymysql
from pymysql.cursors import DictCursor

from src.config import DatabaseConfig, config as app_config
from src.exceptions import DatabaseConfigurationError

logger = logging.getLogger(__name__)


def create_connection(db_config: Optional[DatabaseConfig] = None) -> pymysql.Connection:
    """Cria e retorna uma conexão direta com o MySQL usando DictCursor."""
    cfg = db_config or app_config.db
    try:
        connection = pymysql.connect(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            charset=cfg.charset,
            connect_timeout=cfg.connect_timeout,
            cursorclass=DictCursor,
            autocommit=False,
        )
        return connection
    except pymysql.MySQLError as exc:
        logger.error("Erro ao conectar ao MySQL (%s:%s/%s): %s", cfg.host, cfg.port, cfg.database, exc)
        raise DatabaseConfigurationError(str(exc)) from exc


@contextmanager
def get_db_connection(db_config: Optional[DatabaseConfig] = None) -> Generator[pymysql.Connection, None, None]:
    """Context manager para conexões gerenciadas com commit/rollback automático."""
    conn = create_connection(db_config)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_db_cursor(
    connection: Optional[pymysql.Connection] = None,
    db_config: Optional[DatabaseConfig] = None,
) -> Generator[DictCursor, None, None]:
    """Context manager que fornece um DictCursor.
    
    Se uma conexão for fornecida, utiliza-a sem fechá-la.
    Caso contrário, abre uma nova conexão temporária gerenciada.
    """
    if connection is not None:
        cursor = connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()
    else:
        with get_db_connection(db_config) as conn:
            cursor = conn.cursor()
            try:
                yield cursor
            finally:
                cursor.close()
