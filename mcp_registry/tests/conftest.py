# запуск POSTGRES_HOST=127.0.0.1 uv run python -m pytest mcp_registry/tests -v

from __future__ import annotations

import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from sqlalchemy import text

from DB import DatabaseConfig, PostgresDatabase
from mcp_registry import McpServerStore

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Ключ шифрования для тестов — генерируется один раз на весь тестовый прогон,
# не зависит от .env, чтобы тесты не ломались из-за отсутствия/несовпадения реального ключа.
os.environ.setdefault("MCP_SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture(scope="session")
def database() -> PostgresDatabase:
    """Подключается к тестовой базе и применяет все Alembic-миграции один раз на всю сессию тестов."""
    config = DatabaseConfig.from_env()
    db = PostgresDatabase(config)
    db.open()
    db.migrate()
    yield db
    db.close()


@pytest.fixture(autouse=True)
def clean_tables(database: PostgresDatabase):
    """Очищает таблицу mcp_servers ПОСЛЕ каждого теста, чтобы тесты не влияли друг на друга."""
    yield
    with database.session() as session:
        session.execute(text("TRUNCATE TABLE mcp_servers RESTART IDENTITY CASCADE;"))


@pytest.fixture
def store(database: PostgresDatabase) -> McpServerStore:
    return McpServerStore(database)


@pytest.fixture
def encryption_key() -> str:
    """Реальное значение ключа шифрования, используемого в текущем тестовом прогоне."""
    return os.environ["MCP_SECRETS_ENCRYPTION_KEY"]
