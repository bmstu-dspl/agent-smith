from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import DDL, Engine, create_engine, event, func, literal, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ._config import DatabaseConfig
from ._errors import DatabaseConnectionError, DatabaseQueryError


class PostgresDatabase:
    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def config(self) -> DatabaseConfig:
        return self._config

    @property
    def engine(self) -> Engine:
        self._ensure_open()
        assert self._engine is not None
        return self._engine

    @property
    def is_open(self) -> bool:
        return self._engine is not None

    def open(self) -> None:
        if self._engine is not None:
            return

        try:
            engine = create_engine(
                _sqlalchemy_dsn(self._config.dsn),
                pool_size=self._config.pool_size,
                max_overflow=self._config.max_overflow,
                pool_timeout=self._config.pool_timeout_seconds,
                pool_recycle=int(self._config.pool_recycle_seconds),
                pool_pre_ping=True,
                connect_args={"connect_timeout": self._config.connect_timeout_seconds},
            )
            if self._config.session_statements:
                event.listen(engine, "connect", self._configure_connection)
            with engine.connect() as connection:
                connection.execute(select(literal(1)))
        except (DBAPIError, SQLAlchemyError) as error:
            raise DatabaseConnectionError("failed to open PostgreSQL connection pool") from error

        self._engine = engine
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def close(self) -> None:
        if self._engine is None:
            return
        self._engine.dispose()
        self._engine = None
        self._session_factory = None

    def healthcheck(self) -> dict[str, object]:
        statement = select(
            func.current_database().label("database_name"),
            func.current_schema().label("schema_name"),
            func.version().label("server_version"),
        )
        with self._connection() as connection:
            row = connection.execute(statement).mappings().one()
            return dict(row)

    def initialize(self, *, ensure_vector_extension: bool = False) -> None:
        self.open()
        if ensure_vector_extension:
            with self.engine.begin() as connection:
                connection.execute(DDL("CREATE EXTENSION IF NOT EXISTS vector"))

    def migrate(self, revision: str = "head") -> None:
        from ._migrations import Migrator

        Migrator(self).upgrade(revision)

    @contextmanager
    def session(self) -> Iterator[Session]:
        self._ensure_open()
        assert self._session_factory is not None
        session = self._session_factory()
        try:
            with session.begin():
                yield session
        except SQLAlchemyError as error:
            raise DatabaseQueryError("database transaction failed") from error
        finally:
            session.close()

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        try:
            with self.engine.connect() as connection:
                yield connection
        except SQLAlchemyError as error:
            raise DatabaseConnectionError("failed to acquire PostgreSQL connection") from error

    def _configure_connection(self, dbapi_connection: Any, _: Any) -> None:
        with dbapi_connection.cursor() as cursor:
            for statement in self._config.session_statements:
                cursor.execute(statement)
        dbapi_connection.commit()

    def _ensure_open(self) -> None:
        if self._engine is None:
            raise DatabaseConnectionError("database pool is not open")


def _sqlalchemy_dsn(dsn: str) -> str:
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    return dsn
