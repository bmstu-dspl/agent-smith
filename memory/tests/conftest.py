from __future__ import annotations

from pathlib import Path

import pytest

from DB import DatabaseConfig, Migrator, PostgresDatabase
from memory.messages_store import MessagesStore
from memory.procedural_store import ProceduralStore


@pytest.fixture(scope="session")
def database() -> PostgresDatabase:
    """Подключается к тестовой базе (см. POSTGRES_* в .env.test) и применяет миграции памяти один раз на всю сессию тестов."""
    config = DatabaseConfig.from_env()
    db = PostgresDatabase(config)
    db.open()
    migrations_path = Path(__file__).resolve().parent.parent / "migrations"
    db.apply_migrations(Migrator(migrations_path=migrations_path).load())
    yield db
    db.close()


@pytest.fixture(autouse=True)
def clean_tables(database: PostgresDatabase):
    """Очищает таблицы ПОСЛЕ каждого теста, чтобы тесты не влияли друг на друга."""
    yield
    database.execute("TRUNCATE TABLE messages RESTART IDENTITY CASCADE;")
    database.execute("TRUNCATE TABLE system_settings RESTART IDENTITY CASCADE;")


@pytest.fixture
def messages_store(database: PostgresDatabase) -> MessagesStore:
    return MessagesStore(database)


@pytest.fixture
def procedural_store(database: PostgresDatabase) -> ProceduralStore:
    return ProceduralStore(database)