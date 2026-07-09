from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock, patch

from app_runtime import AppRuntime


class AppRuntimeTestCase(TestCase):
    @patch("app_runtime.MemoryModule")
    @patch("app_runtime.PostgresDocumentStore")
    @patch("app_runtime.Migrator")
    @patch("app_runtime.PostgresDatabase")
    @patch("app_runtime.DatabaseConfig")
    def test_from_env_bootstraps_database_and_memory(
        self,
        database_config_cls: MagicMock,
        postgres_database_cls: MagicMock,
        migrator_cls: MagicMock,
        postgres_store_cls: MagicMock,
        memory_module_cls: MagicMock,
    ) -> None:
        config = object()
        database = MagicMock()
        migrations = [object()]
        store = object()
        memory = object()

        database_config_cls.from_env.return_value = config
        postgres_database_cls.return_value = database
        migrator_cls.return_value.load.return_value = migrations
        postgres_store_cls.return_value = store
        memory_module_cls.return_value = memory

        runtime = AppRuntime.from_env()

        self.assertIs(runtime.database, database)
        self.assertIs(runtime.memory, memory)
        database.open.assert_called_once_with()
        database.apply_migrations.assert_called_once_with(migrations)
        postgres_store_cls.assert_called_once_with(database)
        memory_module_cls.assert_called_once_with(store)

    def test_close_delegates_to_database(self) -> None:
        database = MagicMock()
        runtime = AppRuntime(database=database, memory=object())

        runtime.close()

        database.close.assert_called_once_with()
