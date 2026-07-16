from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from ._errors import DatabaseConfigurationError


@dataclass(slots=True, frozen=True)
class DatabaseConfig:
    dsn: str
    pool_size: int = 5
    max_overflow: int = 10
    connect_timeout_seconds: float = 5.0
    pool_timeout_seconds: float = 10.0
    pool_recycle_seconds: float = 3600.0
    session_statements: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        dsn = self.dsn.strip()
        if not dsn:
            raise DatabaseConfigurationError("database dsn must not be empty")
        object.__setattr__(self, "dsn", dsn)

        if self.pool_size <= 0:
            raise DatabaseConfigurationError("pool_size must be positive")
        if self.max_overflow < 0:
            raise DatabaseConfigurationError("max_overflow must not be negative")
        if self.connect_timeout_seconds <= 0:
            raise DatabaseConfigurationError("connect_timeout_seconds must be positive")
        if self.pool_timeout_seconds <= 0:
            raise DatabaseConfigurationError("pool_timeout_seconds must be positive")
        if self.pool_recycle_seconds <= 0:
            raise DatabaseConfigurationError("pool_recycle_seconds must be positive")

    @classmethod
    def from_env(cls, prefix: str = "POSTGRES_") -> DatabaseConfig:
        env = os.environ
        dsn = _read_value(env, f"{prefix}DSN")
        if dsn:
            return cls(
                dsn=dsn,
                pool_size=int(env.get(f"{prefix}POOL_SIZE", "5")),
                max_overflow=int(env.get(f"{prefix}MAX_OVERFLOW", "10")),
                connect_timeout_seconds=float(env.get(f"{prefix}CONNECT_TIMEOUT", "5")),
                pool_timeout_seconds=float(env.get(f"{prefix}POOL_TIMEOUT", "10")),
                pool_recycle_seconds=float(env.get(f"{prefix}POOL_RECYCLE", "3600")),
                session_statements=_read_session_statements(env, prefix),
            )

        required = ("HOST", "PORT", "DB", "USER", "PASSWORD")
        values = {name: _read_value(env, f"{prefix}{name}") for name in required}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise DatabaseConfigurationError(
                f"missing database env vars: {', '.join(f'{prefix}{name}' for name in missing)}"
            )

        host = values["HOST"]
        port = values["PORT"]
        database = values["DB"]
        user = values["USER"]
        password = values["PASSWORD"]
        assert host and port and database and user and password
        dsn = (
            f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
            f"@{host}:{port}/{quote(database, safe='')}"
        )

        return cls(
            dsn=dsn,
            pool_size=int(env.get(f"{prefix}POOL_SIZE", "5")),
            max_overflow=int(env.get(f"{prefix}MAX_OVERFLOW", "10")),
            connect_timeout_seconds=float(env.get(f"{prefix}CONNECT_TIMEOUT", "5")),
            pool_timeout_seconds=float(env.get(f"{prefix}POOL_TIMEOUT", "10")),
            pool_recycle_seconds=float(env.get(f"{prefix}POOL_RECYCLE", "3600")),
            session_statements=_read_session_statements(env, prefix),
        )


def _read_session_statements(env: os._Environ[str], prefix: str) -> tuple[str, ...]:
    raw = env.get(f"{prefix}SESSION_STATEMENTS", "")
    return tuple(statement.strip() for statement in raw.split(";") if statement.strip())


def _read_value(env: os._Environ[str], key: str) -> str | None:
    value = env.get(key)
    if value:
        return value.strip()

    file_path = env.get(f"{key}_FILE")
    if not file_path:
        return None
    try:
        secret = Path(file_path).read_text(encoding="utf-8").strip()
    except OSError as error:
        raise DatabaseConfigurationError(f"failed to read {key}_FILE") from error
    if not secret:
        raise DatabaseConfigurationError(f"{key}_FILE must not be empty")
    return secret
