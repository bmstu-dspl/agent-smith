from __future__ import annotations

import os
from dataclasses import dataclass, field

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
        dsn = env.get(f"{prefix}DSN")
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
        missing = [name for name in required if not env.get(f"{prefix}{name}")]
        if missing:
            raise DatabaseConfigurationError(
                f"missing database env vars: {', '.join(f'{prefix}{name}' for name in missing)}"
            )

        host = env[f"{prefix}HOST"]
        port = env[f"{prefix}PORT"]
        database = env[f"{prefix}DB"]
        user = env[f"{prefix}USER"]
        password = env[f"{prefix}PASSWORD"]
        dsn = f"postgresql://{user}:{password}@{host}:{port}/{database}"

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
