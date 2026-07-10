from __future__ import annotations

import os
from pathlib import Path
from unittest import TestCase
from uuid import uuid4

from dotenv import dotenv_values

from DB import DatabaseConfig, GraphEdge, GraphNode, GraphStore, Migrator, PostgresDatabase


class PostgresDatabaseIntegrationTestCase(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._env_path = Path(__file__).resolve().parents[2] / ".env"
        cls._env = {
            key: value
            for key, value in dotenv_values(cls._env_path).items()
            if value is not None
        }
        cls._schema = f"test_db_{uuid4().hex[:12]}"
        cls._database = PostgresDatabase(
            DatabaseConfig(
                dsn=_dsn_from_env(cls._env),
                min_pool_size=1,
                max_pool_size=4,
                session_statements=(f"SET search_path TO {cls._schema}, public",),
            )
        )
        cls._database.open()
        cls._database.execute(f'CREATE SCHEMA "{cls._schema}";')
        cls._database.apply_migrations(Migrator().load())
        cls._graph = GraphStore(cls._database)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._database.execute(f'DROP SCHEMA IF EXISTS "{cls._schema}" CASCADE;')
        cls._database.close()

    def test_healthcheck(self) -> None:
        health = self._database.healthcheck()
        self.assertIn("database_name", health)
        self.assertEqual(health["schema_name"], self._schema)

    def test_execute_and_fetch_roundtrip(self) -> None:
        result = self._database.execute(
            """
            CREATE TABLE IF NOT EXISTS integration_notes (
                id TEXT PRIMARY KEY,
                body TEXT NOT NULL,
                embedding vector(3)
            );
            """
        )
        self.assertGreaterEqual(result.rows_affected, 0)

        self._database.execute(
            """
            INSERT INTO integration_notes (id, body, embedding)
            VALUES (%s, %s, '[1,2,3]')
            ON CONFLICT (id) DO UPDATE SET body = EXCLUDED.body;
            """,
            ("note-1", "first note"),
        )

        row = self._database.fetch_one(
            """
            SELECT id, body, embedding::text AS embedding
            FROM integration_notes
            WHERE id = %s;
            """,
            ("note-1",),
        )
        self.assertEqual(row, {"id": "note-1", "body": "first note", "embedding": "[1,2,3]"})

    def test_executemany_and_fetch_all(self) -> None:
        self._database.execute(
            """
            CREATE TABLE IF NOT EXISTS batch_notes (
                id TEXT PRIMARY KEY,
                body TEXT NOT NULL
            );
            """
        )
        result = self._database.executemany(
            "INSERT INTO batch_notes (id, body) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING;",
            [("note-2", "second note"), ("note-3", "third note")],
        )
        self.assertGreaterEqual(result.rows_affected, 0)

        rows = self._database.fetch_all(
            "SELECT id, body FROM batch_notes WHERE id IN (%s, %s) ORDER BY id;",
            ("note-2", "note-3"),
        )
        self.assertEqual(
            rows,
            [
                {"id": "note-2", "body": "second note"},
                {"id": "note-3", "body": "third note"},
            ],
        )

    def test_transaction_rolls_back_on_error(self) -> None:
        self._database.execute(
            """
            CREATE TABLE IF NOT EXISTS rollback_notes (
                id TEXT PRIMARY KEY,
                body TEXT NOT NULL
            );
            """
        )
        with self.assertRaises(RuntimeError):
            with self._database.transaction() as connection:
                connection.execute(
                    "INSERT INTO rollback_notes (id, body) VALUES (%s, %s);",
                    ("note-rollback", "should disappear"),
                )
                raise RuntimeError("boom")

        row = self._database.fetch_one(
            "SELECT id FROM rollback_notes WHERE id = %s;",
            ("note-rollback",),
        )
        self.assertIsNone(row)

    def test_graph_store_roundtrip_and_traversal(self) -> None:
        self._graph.upsert_node(GraphNode(node_id="user-1", node_type="user", properties={"name": "Alice"}))
        self._graph.upsert_node(GraphNode(node_id="project-1", node_type="project", properties={"name": "Smith"}))
        self._graph.upsert_node(GraphNode(node_id="doc-1", node_type="document", properties={"title": "Spec"}))
        self._graph.upsert_edge(
            GraphEdge(
                edge_id="edge-1",
                from_node_id="user-1",
                to_node_id="project-1",
                edge_type="owns",
                properties={"role": "owner"},
            )
        )
        self._graph.upsert_edge(
            GraphEdge(
                edge_id="edge-2",
                from_node_id="project-1",
                to_node_id="doc-1",
                edge_type="contains",
                properties={},
            )
        )

        node = self._graph.get_node("user-1")
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node["properties"]["name"], "Alice")

        neighbors = self._graph.get_neighbors("user-1")
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0]["node_id"], "project-1")

        traversal = self._graph.traverse("user-1", max_depth=3)
        self.assertEqual([row["to_node_id"] for row in traversal], ["project-1", "doc-1"])


def _dsn_from_env(env: dict[str, str]) -> str:
    direct_dsn = os.environ.get("DB_TEST_POSTGRES_DSN")
    if direct_dsn:
        return direct_dsn

    for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PORT"):
        if not env.get(key):
            raise ValueError(f"missing {key} in .env")

    host = os.environ.get("DB_TEST_POSTGRES_HOST") or os.environ.get("POSTGRES_HOST") or "127.0.0.1"
    port = os.environ.get("DB_TEST_POSTGRES_PORT") or env["POSTGRES_PORT"]
    user = os.environ.get("DB_TEST_POSTGRES_USER") or env["POSTGRES_USER"]
    password = os.environ.get("DB_TEST_POSTGRES_PASSWORD") or env["POSTGRES_PASSWORD"]
    database = os.environ.get("DB_TEST_POSTGRES_DB") or env["POSTGRES_DB"]
    return (
        f"postgresql://{user}:{password}"
        f"@{host}:{port}/{database}"
    )
