from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import MagicMock, patch

from app_runtime import AppRuntime


class AppRuntimeTestCase(TestCase):
    @patch("app_runtime.GoogleEmbeddingProvider")
    @patch("app_runtime.GoogleEmbeddingConfig")
    @patch("app_runtime.MemoryModule")
    @patch("app_runtime.PostgresDocumentStore")
    @patch("app_runtime.PostgresDatabase")
    @patch("app_runtime.DatabaseConfig")
    def test_from_env_bootstraps_database_and_memory(
        self,
        database_config_cls: MagicMock,
        postgres_database_cls: MagicMock,
        postgres_store_cls: MagicMock,
        memory_module_cls: MagicMock,
        embedding_config_cls: MagicMock,
        embedding_provider_cls: MagicMock,
    ) -> None:
        config = object()
        database = MagicMock()
        store = object()
        memory = object()
        embedding_provider = MagicMock()

        database_config_cls.from_env.return_value = config
        postgres_database_cls.return_value = database
        postgres_store_cls.return_value = store
        memory_module_cls.return_value = memory
        embedding_provider_cls.return_value = embedding_provider

        runtime = AppRuntime.from_env()

        self.assertIs(runtime.database, database)
        self.assertIs(runtime.memory, memory)
        self.assertIs(runtime.embedding_provider, embedding_provider)
        database.open.assert_called_once_with()
        database.migrate.assert_called_once_with()
        postgres_store_cls.assert_called_once_with(database)
        memory_module_cls.assert_called_once_with(store, embedding_provider=embedding_provider)

    def test_close_delegates_to_database(self) -> None:
        database = MagicMock()
        embedding_provider = MagicMock()
        runtime = AppRuntime(
            database=database,
            memory=object(),
            embedding_provider=embedding_provider,
        )

        runtime.close()

        embedding_provider.close.assert_called_once_with()
        database.close.assert_called_once_with()

    @patch("app_runtime.GoogleEmbeddingProvider")
    @patch("app_runtime.GoogleEmbeddingConfig")
    @patch("app_runtime.PostgresDatabase")
    @patch("app_runtime.DatabaseConfig")
    def test_from_env_closes_resources_when_migration_fails(
        self,
        database_config_cls: MagicMock,
        postgres_database_cls: MagicMock,
        embedding_config_cls: MagicMock,
        embedding_provider_cls: MagicMock,
    ) -> None:
        database = MagicMock()
        database.migrate.side_effect = RuntimeError("migration failed")
        embedding_provider = MagicMock()
        postgres_database_cls.return_value = database
        embedding_provider_cls.return_value = embedding_provider

        with self.assertRaisesRegex(RuntimeError, "migration failed"):
            AppRuntime.from_env()

        database.close.assert_called_once_with()
        embedding_provider.close.assert_called_once_with()

    @patch.dict(os.environ, {"RUN_DB_MIGRATIONS": "false"})
    @patch("app_runtime.GoogleEmbeddingProvider")
    @patch("app_runtime.GoogleEmbeddingConfig")
    @patch("app_runtime.MemoryModule")
    @patch("app_runtime.PostgresDocumentStore")
    @patch("app_runtime.PostgresDatabase")
    @patch("app_runtime.DatabaseConfig")
    def test_from_env_can_skip_migrations(
        self,
        database_config_cls: MagicMock,
        postgres_database_cls: MagicMock,
        postgres_store_cls: MagicMock,
        memory_module_cls: MagicMock,
        embedding_config_cls: MagicMock,
        embedding_provider_cls: MagicMock,
    ) -> None:
        database = MagicMock()
        postgres_database_cls.return_value = database

        AppRuntime.from_env()

        database.open.assert_called_once_with()
        database.migrate.assert_not_called()
