from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence

from psycopg import Connection, sql
from psycopg.errors import Error as PsycopgError
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from ._config import DatabaseConfig
from ._errors import DatabaseConnectionError, DatabaseQueryError, MigrationError
from ._migrations import Migration


@dataclass(slots=True, frozen=True)
class QueryResult:
    rows_affected: int
    last_row_id: int | None = None


class PostgresDatabase:
    def __init__(
        self,
        config: DatabaseConfig,
        *,
        pool_class: type[ConnectionPool[Connection[dict[str, Any]]]] = ConnectionPool,
    ) -> None:
        self._config = config
        self._pool_class = pool_class
        self._pool: ConnectionPool[Connection[dict[str, Any]]] | None = None

    @property
    def config(self) -> DatabaseConfig:
        return self._config

    @property
    def is_open(self) -> bool:
        return self._pool is not None

    def open(self) -> None:
        if self._pool is not None:
            return

        try:
            pool = self._pool_class(
                conninfo=self._config.dsn,
                min_size=self._config.min_pool_size,
                max_size=self._config.max_pool_size,
                timeout=self._config.pool_wait_timeout_seconds,
                max_waiting=self._config.max_waiting,
                max_lifetime=self._config.max_lifetime_seconds,
                max_idle=self._config.max_idle_seconds,
                num_workers=self._config.num_workers,
                open=False,
                kwargs={
                    "connect_timeout": self._config.connect_timeout_seconds,
                    "row_factory": dict_row,
                },
                configure=self._configure_connection,
                check=ConnectionPool.check_connection,
            )
            pool.open(wait=True, timeout=self._config.pool_wait_timeout_seconds)
        except (PoolTimeout, PsycopgError) as error:
            raise DatabaseConnectionError("failed to open PostgreSQL connection pool") from error

        self._pool = pool

    def close(self) -> None:
        if self._pool is None:
            return
        self._pool.close()
        self._pool = None

    def healthcheck(self) -> dict[str, object]:
        row = self.fetch_one("SELECT current_database() AS database_name, current_schema() AS schema_name, version() AS server_version;")
        if row is None:
            raise DatabaseConnectionError("healthcheck returned no data")
        return row

    def initialize(self, *, ensure_vector_extension: bool = False) -> None:
        self.open()
        if ensure_vector_extension:
            self.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    def apply_migrations(self, migrations: Sequence[Migration]) -> list[str]:
        self._ensure_open()
        self._ensure_migrations_table()

        applied_versions = {
            row["version"]
            for row in self.fetch_all("SELECT version FROM schema_migrations ORDER BY version;")
        }
        newly_applied: list[str] = []

        for migration in migrations:
            if migration.version in applied_versions:
                continue

            try:
                with self.transaction() as connection:
                    connection.execute(migration.sql)
                    connection.execute(
                        """
                        INSERT INTO schema_migrations (version, name)
                        VALUES (%s, %s);
                        """,
                        (migration.version, migration.name),
                    )
            except PsycopgError as error:
                raise MigrationError(f"failed to apply migration {migration.version}_{migration.name}") from error

            newly_applied.append(migration.version)

        return newly_applied

    @contextmanager
    def connection(self) -> Iterator[Connection[dict[str, Any]]]:
        self._ensure_open()
        assert self._pool is not None
        try:
            with self._pool.connection() as connection:
                yield connection
        except (PoolTimeout, PsycopgError) as error:
            raise DatabaseConnectionError("failed to acquire PostgreSQL connection") from error

    @contextmanager
    def transaction(self) -> Iterator[Connection[dict[str, Any]]]:
        with self.connection() as connection:
            try:
                with connection.transaction():
                    yield connection
            except PsycopgError as error:
                raise DatabaseQueryError("transaction failed") from error

    def execute(
        self,
        sql_query: str,
        parameters: Sequence[object] | Mapping[str, object] = (),
    ) -> QueryResult:
        try:
            with self.transaction() as connection:
                cursor = connection.execute(sql_query, parameters)
                return QueryResult(
                    rows_affected=cursor.rowcount if cursor.rowcount >= 0 else 0,
                    last_row_id=None,
                )
        except PsycopgError as error:
            raise DatabaseQueryError("query execution failed") from error

    def executemany(
        self,
        sql_query: str,
        parameters: Sequence[Sequence[object] | Mapping[str, object]],
    ) -> QueryResult:
        try:
            with self.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.executemany(sql_query, parameters)
                    return QueryResult(rows_affected=cursor.rowcount if cursor.rowcount >= 0 else 0)
        except PsycopgError as error:
            raise DatabaseQueryError("batch query execution failed") from error

    def fetch_one(
        self,
        sql_query: str,
        parameters: Sequence[object] | Mapping[str, object] = (),
    ) -> dict[str, object] | None:
        try:
            with self.connection() as connection:
                row = connection.execute(sql_query, parameters).fetchone()
                return row if row is not None else None
        except PsycopgError as error:
            raise DatabaseQueryError("query fetch failed") from error

    def fetch_all(
        self,
        sql_query: str,
        parameters: Sequence[object] | Mapping[str, object] = (),
    ) -> list[dict[str, object]]:
        try:
            with self.connection() as connection:
                rows = connection.execute(sql_query, parameters).fetchall()
                return list(rows)
        except PsycopgError as error:
            raise DatabaseQueryError("query fetch failed") from error

    def quote_identifier(self, identifier: str) -> str:
        if not identifier.strip():
            raise DatabaseQueryError("identifier must not be empty")
        with self.connection() as connection:
            return sql.Identifier(identifier).as_string(connection)

    def _configure_connection(self, connection: Connection[dict[str, Any]]) -> None:
        for statement in self._config.session_statements:
            connection.execute(statement)
        if self._config.session_statements:
            connection.commit()

    def _ensure_open(self) -> None:
        if self._pool is None:
            raise DatabaseConnectionError("database pool is not open")

    def _ensure_migrations_table(self) -> None:
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
