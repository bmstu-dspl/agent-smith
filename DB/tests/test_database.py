from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import patch

from DB import (
    DatabaseConfig,
    DatabaseConfigurationError,
    GraphEdge,
    GraphNode,
    Migration,
    Migrator,
    PostgresDatabase,
)
from DB._graph import _json


class DatabaseConfigTestCase(TestCase):
    def test_from_env_builds_dsn(self) -> None:
        with patch.dict(
            os.environ,
            {
                "POSTGRES_HOST": "localhost",
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "agent_smith",
                "POSTGRES_USER": "agent_smith",
                "POSTGRES_PASSWORD": "secret",
                "POSTGRES_MIN_POOL_SIZE": "2",
                "POSTGRES_MAX_POOL_SIZE": "8",
                "POSTGRES_SESSION_STATEMENTS": "SET search_path TO public;SET TIME ZONE 'UTC'",
            },
            clear=True,
        ):
            config = DatabaseConfig.from_env()

        self.assertEqual(config.dsn, "postgresql://agent_smith:secret@localhost:5432/agent_smith")
        self.assertEqual(config.min_pool_size, 2)
        self.assertEqual(config.max_pool_size, 8)
        self.assertEqual(config.session_statements, ("SET search_path TO public", "SET TIME ZONE 'UTC'"))

    def test_from_env_requires_values(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(DatabaseConfigurationError):
                DatabaseConfig.from_env()

    @patch("DB._config.Path.read_text", return_value="p@ss word\n")
    def test_from_env_reads_password_file(self, read_text) -> None:
        with patch.dict(
            os.environ,
            {
                "POSTGRES_HOST": "postgres",
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "agent_smith",
                "POSTGRES_USER": "agent_smith",
                "POSTGRES_PASSWORD_FILE": "/run/secrets/postgres_password",
            },
            clear=True,
        ):
            config = DatabaseConfig.from_env()

        self.assertEqual(
            config.dsn,
            "postgresql://agent_smith:p%40ss%20word@postgres:5432/agent_smith",
        )
        read_text.assert_called_once_with(encoding="utf-8")


class MigratorTestCase(TestCase):
    def test_load_migrations(self) -> None:
        migrations = Migrator().load()
        self.assertGreaterEqual(len(migrations), 2)
        self.assertEqual(migrations[0].version, "0001")


class GraphValueObjectsTestCase(TestCase):
    def test_json_serializer_is_stable(self) -> None:
        payload = _json({"b": 2, "a": 1})
        self.assertEqual(payload, '{"a": 1, "b": 2}')

    def test_graph_records_are_constructible(self) -> None:
        node = GraphNode(node_id="user-1", node_type="user", properties={"name": "Alice"})
        edge = GraphEdge(
            edge_id="edge-1",
            from_node_id="user-1",
            to_node_id="project-1",
            edge_type="owns",
            properties={"role": "owner"},
        )

        self.assertEqual(node.node_type, "user")
        self.assertEqual(edge.edge_type, "owns")


class PostgresDatabaseLifecycleTestCase(TestCase):
    def test_quote_identifier_requires_open_pool(self) -> None:
        database = PostgresDatabase(DatabaseConfig(dsn="postgresql://user:password@localhost:5432/rag"))
        with self.assertRaisesRegex(Exception, "pool is not open"):
            database.quote_identifier("graph_nodes")
