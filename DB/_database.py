from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Mapping, Sequence

from psycopg import Connection, connect
from psycopg.rows import dict_row


@dataclass(slots=True, frozen=True)
class DatabaseConfig:
    dsn: str
    pragmas: tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        normalized_dsn = self.dsn.strip()
        if not normalized_dsn:
            raise ValueError("database dsn must not be empty")
        object.__setattr__(self, "dsn", normalized_dsn)
        if self.timeout_seconds <= 0:
            raise ValueError("database timeout must be positive")


@dataclass(slots=True, frozen=True)
class QueryResult:
    rows_affected: int
    last_row_id: int | None = None


class PostgresDatabase:
    def __init__(
        self,
        config: DatabaseConfig,
        *,
        connection_factory: Callable[..., Connection[Any]] | None = None,
    ) -> None:
        self._config = config
        self._connection_factory = connection_factory or connect

    @property
    def config(self) -> DatabaseConfig:
        return self._config

    def initialize(self) -> None:
        with self.connection() as connection:
            self._apply_session_settings(connection)

    @contextmanager
    def connection(self) -> Iterator[Connection[Any]]:
        connection = self._connection_factory(
            self._config.dsn,
            connect_timeout=self._config.timeout_seconds,
            row_factory=dict_row,
        )
        try:
            self._apply_session_settings(connection)
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[Connection[Any]]:
        with self.connection() as connection:
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def execute(
        self,
        sql: str,
        parameters: Sequence[object] | Mapping[str, object] = (),
    ) -> QueryResult:
        with self.transaction() as connection:
            cursor = connection.execute(sql, parameters)
            return QueryResult(
                rows_affected=cursor.rowcount if cursor.rowcount >= 0 else 0,
                last_row_id=None,
            )

    def executemany(
        self,
        sql: str,
        parameters: Sequence[Sequence[object] | Mapping[str, object]],
    ) -> QueryResult:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(sql, parameters)
                return QueryResult(rows_affected=cursor.rowcount if cursor.rowcount >= 0 else 0)

    def fetch_one(
        self,
        sql: str,
        parameters: Sequence[object] | Mapping[str, object] = (),
    ) -> dict[str, object] | None:
        with self.connection() as connection:
            row = connection.execute(sql, parameters).fetchone()
            return row if row is not None else None

    def fetch_all(
        self,
        sql: str,
        parameters: Sequence[object] | Mapping[str, object] = (),
    ) -> list[dict[str, object]]:
        with self.connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
            return list(rows)

    def script(self, sql: str) -> None:
        with self.transaction() as connection:
            connection.execute(sql)

    def _apply_session_settings(self, connection: Connection[Any]) -> None:
        for statement in self._config.pragmas:
            connection.execute(statement)
