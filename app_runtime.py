from __future__ import annotations

import os
from dataclasses import dataclass

from DB import DatabaseConfig, PostgresDatabase
from RAG import (
    GoogleEmbeddingConfig,
    GoogleEmbeddingProvider,
    MemoryModule,
    PostgresDocumentStore,
)


@dataclass(slots=True)
class AppRuntime:
    database: PostgresDatabase
    memory: MemoryModule
    embedding_provider: GoogleEmbeddingProvider

    @classmethod
    def from_env(cls) -> AppRuntime:
        embedding_config = GoogleEmbeddingConfig.from_env()
        database_config = DatabaseConfig.from_env()
        embedding_provider = GoogleEmbeddingProvider(embedding_config)
        database = PostgresDatabase(database_config)
        try:
            database.open()
            if _env_bool("RUN_DB_MIGRATIONS", default=True):
                database.migrate()
            memory = MemoryModule(
                PostgresDocumentStore(database),
                embedding_provider=embedding_provider,
            )
        except Exception:
            database.close()
            embedding_provider.close()
            raise
        return cls(
            database=database,
            memory=memory,
            embedding_provider=embedding_provider,
        )

    def close(self) -> None:
        self.embedding_provider.close()
        self.database.close()


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
