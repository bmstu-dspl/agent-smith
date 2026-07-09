from __future__ import annotations

from dataclasses import dataclass

from DB import DatabaseConfig, Migrator, PostgresDatabase
from RAG import MemoryModule, PostgresDocumentStore


@dataclass(slots=True)
class AppRuntime:
    database: PostgresDatabase
    memory: MemoryModule

    @classmethod
    def from_env(cls) -> AppRuntime:
        database = PostgresDatabase(DatabaseConfig.from_env())
        database.open()
        database.apply_migrations(Migrator().load())

        memory = MemoryModule(PostgresDocumentStore(database))
        return cls(database=database, memory=memory)

    def close(self) -> None:
        self.database.close()
