from __future__ import annotations

import os
from dataclasses import dataclass

from DB import DatabaseConfig, PostgresDatabase
from RAG import MemoryModule, PostgresDocumentStore


@dataclass(slots=True)
class AppRuntime:
    database: PostgresDatabase
    memory: MemoryModule

    @classmethod
    def from_env(cls) -> AppRuntime:
        database = PostgresDatabase(DatabaseConfig.from_env())
        database.open()
        if _env_bool("RUN_DB_MIGRATIONS", default=True):
            database.migrate()

        memory = MemoryModule(PostgresDocumentStore(database))
        return cls(database=database, memory=memory)

    def close(self) -> None:
        self.database.close()


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
