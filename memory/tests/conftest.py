#запуск  POSTGRES_HOST=127.0.0.1 uv run python -m pytest memory/tests ai_core/tests -v
from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import text

from DB import DatabaseConfig, PostgresDatabase
from memory.messages_store import MessagesStore
from memory.procedural_store import ProceduralStore

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@pytest.fixture(scope="session")
def database() -> PostgresDatabase:
    """Подключается к тестовой базе (см. POSTGRES_* в .env) и применяет все Alembic-миграции один раз на всю сессию тестов."""
    config = DatabaseConfig.from_env()
    db = PostgresDatabase(config)
    db.open()
    db.migrate()
    yield db
    db.close()


@pytest.fixture(autouse=True)
def clean_tables(database: PostgresDatabase):
    """Очищает таблицы ПОСЛЕ каждого теста, чтобы тесты не влияли друг на друга."""
    yield
    with database.session() as session:
        session.execute(text("TRUNCATE TABLE messages RESTART IDENTITY CASCADE;"))
        session.execute(text("TRUNCATE TABLE system_settings RESTART IDENTITY CASCADE;"))


@pytest.fixture
def messages_store(database: PostgresDatabase) -> MessagesStore:
    return MessagesStore(database)


@pytest.fixture
def procedural_store(database: PostgresDatabase) -> ProceduralStore:
    return ProceduralStore(database)
