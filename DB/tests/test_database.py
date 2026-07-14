from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import patch

from DB import (
    DatabaseConfig,
    DatabaseConfigurationError,
    GraphEdge,
    GraphNode,
    PostgresDatabase,
)


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
                "POSTGRES_POOL_SIZE": "8",
                "POSTGRES_MAX_OVERFLOW": "4",
                "POSTGRES_SESSION_STATEMENTS": "SET search_path TO public;SET TIME ZONE 'UTC'",
            },
            clear=True,
        ):
            config = DatabaseConfig.from_env()

        self.assertEqual(config.dsn, "postgresql://agent_smith:secret@localhost:5432/agent_smith")
        self.assertEqual(config.pool_size, 8)
        self.assertEqual(config.max_overflow, 4)
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


class GraphValueObjectsTestCase(TestCase):
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
    def test_engine_requires_open_database(self) -> None:
        database = PostgresDatabase(DatabaseConfig(dsn="postgresql://user:password@localhost:5432/rag"))
        with self.assertRaisesRegex(Exception, "pool is not open"):
            _ = database.engine
