from __future__ import annotations

import os
from pathlib import Path
from unittest import TestCase
from uuid import uuid4

from dotenv import dotenv_values

from DB import DatabaseConfig, PostgresDatabase


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
                pragmas=(f"SET search_path TO {cls._schema}, public;",),
            )
        )

        cls._database.initialize()
        cls._database.execute(f'CREATE SCHEMA "{cls._schema}";')
        cls._database.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cls._database.execute(
            """
            CREATE TABLE integration_notes (
                id TEXT PRIMARY KEY,
                body TEXT NOT NULL,
                embedding vector(3)
            );
            """
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._database.execute(f'DROP SCHEMA IF EXISTS "{cls._schema}" CASCADE;')

    def test_execute_and_fetch_roundtrip(self) -> None:
        result = self._database.execute(
            """
            INSERT INTO integration_notes (id, body, embedding)
            VALUES (%s, %s, '[1,2,3]');
            """,
            ("note-1", "first note"),
        )

        self.assertEqual(result.rows_affected, 1)

        row = self._database.fetch_one(
            """
            SELECT id, body, embedding::text AS embedding
            FROM integration_notes
            WHERE id = %s;
            """,
            ("note-1",),
        )

        self.assertEqual(
            row,
            {"id": "note-1", "body": "first note", "embedding": "[1,2,3]"},
        )

    def test_executemany_and_fetch_all(self) -> None:
        result = self._database.executemany(
            """
            INSERT INTO integration_notes (id, body, embedding)
            VALUES (%s, %s, %s);
            """,
            [
                ("note-2", "second note", "[2,2,2]"),
                ("note-3", "third note", "[3,3,3]"),
            ],
        )

        self.assertGreaterEqual(result.rows_affected, 0)

        rows = self._database.fetch_all(
            """
            SELECT id, body
            FROM integration_notes
            WHERE id IN (%s, %s)
            ORDER BY id;
            """,
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
        with self.assertRaises(RuntimeError):
            with self._database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO integration_notes (id, body, embedding)
                    VALUES (%s, %s, '[9,9,9]');
                    """,
                    ("note-rollback", "should disappear"),
                )
                raise RuntimeError("boom")

        row = self._database.fetch_one(
            "SELECT id FROM integration_notes WHERE id = %s;",
            ("note-rollback",),
        )

        self.assertIsNone(row)

    def test_initialize_applies_search_path(self) -> None:
        self._database.execute(
            """
            INSERT INTO integration_notes (id, body, embedding)
            VALUES (%s, %s, '[4,4,4]')
            ON CONFLICT (id) DO NOTHING;
            """,
            ("note-search-path", "search path note"),
        )

        row = self._database.fetch_one(
            "SELECT body FROM integration_notes WHERE id = %s;",
            ("note-search-path",),
        )

        self.assertEqual(row, {"body": "search path note"})


def _dsn_from_env(env: dict[str, str]) -> str:
    for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PORT"):
        if not env.get(key):
            raise ValueError(f"missing {key} in .env")

    host = os.environ.get("DB_TEST_POSTGRES_HOST") or os.environ.get("POSTGRES_HOST") or "127.0.0.1"
    return (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{host}:{env['POSTGRES_PORT']}/{env['POSTGRES_DB']}"
    )
