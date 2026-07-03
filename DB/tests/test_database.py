from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock

from DB import DatabaseConfig, PostgresDatabase, QueryResult


class PostgresDatabaseTestCase(TestCase):
    def test_execute_and_fetch(self) -> None:
        connection = _FakeConnection()
        database = PostgresDatabase(
            DatabaseConfig(
                dsn="postgresql://user:password@localhost:5432/rag",
                pragmas=("SET search_path TO public;",),
            ),
            connection_factory=lambda *args, **kwargs: connection,
        )

        database.initialize()
        result = database.execute(
            "INSERT INTO documents (id, title) VALUES (%s, %s);",
            ("doc-1", "Architecture"),
        )

        self.assertIsInstance(result, QueryResult)
        self.assertEqual(result.rows_affected, 1)

        row = database.fetch_one(
            "SELECT id, title FROM documents WHERE id = %s;",
            ("doc-1",),
        )
        self.assertEqual(row, {"id": "doc-1", "title": "Architecture"})
        self.assertIn("SET search_path TO public;", connection.executed_sql)

    def test_transaction_rolls_back_on_error(self) -> None:
        connection = _FakeConnection()
        database = PostgresDatabase(
            DatabaseConfig(dsn="postgresql://user:password@localhost:5432/rag"),
            connection_factory=lambda *args, **kwargs: connection,
        )

        with self.assertRaises(RuntimeError):
            with database.transaction() as transaction:
                transaction.execute(
                    "INSERT INTO notes (id, body) VALUES (%s, %s);",
                    ("note-1", "body"),
                )
                raise RuntimeError("boom")

        self.assertTrue(connection.rollback_called)
        self.assertFalse(connection.commit_called)

    def test_executemany_uses_cursor_api(self) -> None:
        connection = _FakeConnection()
        database = PostgresDatabase(
            DatabaseConfig(dsn="postgresql://user:password@localhost:5432/rag"),
            connection_factory=lambda *args, **kwargs: connection,
        )

        result = database.executemany(
            "INSERT INTO notes (id, body) VALUES (%s, %s);",
            [("note-1", "first"), ("note-2", "second")],
        )

        self.assertEqual(result.rows_affected, 2)
        self.assertEqual(connection.cursor_instance.executemany_calls, 1)


class _FakeCursor:
    def __init__(self, sql: str) -> None:
        self.sql = sql
        self.rowcount = 1

    def fetchone(self) -> dict[str, object] | None:
        if "SELECT id, title" in self.sql:
            return {"id": "doc-1", "title": "Architecture"}
        return None

    def fetchall(self) -> list[dict[str, object]]:
        if "SELECT" in self.sql:
            return [{"id": "doc-1", "title": "Architecture"}]
        return []


class _FakeConnection:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []
        self.rollback_called = False
        self.commit_called = False
        self.close = Mock()
        self.cursor_instance = _FakeCursorContextManager()

    def execute(self, sql: str, parameters=()) -> _FakeCursor:
        self.executed_sql.append(sql)
        return _FakeCursor(sql)

    def cursor(self) -> _FakeCursorContextManager:
        return self.cursor_instance

    def rollback(self) -> None:
        self.rollback_called = True

    def commit(self) -> None:
        self.commit_called = True


class _FakeCursorContextManager:
    def __init__(self) -> None:
        self.rowcount = 2
        self.executemany_calls = 0

    def __enter__(self) -> _FakeCursorContextManager:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def executemany(self, sql: str, parameters) -> None:
        self.executemany_calls += 1
