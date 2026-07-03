from __future__ import annotations

import os
from dataclasses import dataclass, field

from ._errors import DatabaseConfigurationError


@dataclass(slots=True, frozen=True)
class DatabaseConfig:
    dsn: str
    min_pool_size: int = 1
    max_pool_size: int = 10
    connect_timeout_seconds: float = 5.0
    pool_wait_timeout_seconds: float = 10.0
    max_idle_seconds: float = 300.0
    max_lifetime_seconds: float = 3600.0
    max_waiting: int = 20
    num_workers: int = 3
    session_statements: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        dsn = self.dsn.strip()
        if not dsn:
            raise DatabaseConfigurationError("database dsn must not be empty")
        object.__setattr__(self, "dsn", dsn)

        if self.min_pool_size <= 0:
            raise DatabaseConfigurationError("min_pool_size must be positive")
        if self.max_pool_size < self.min_pool_size:
            raise DatabaseConfigurationError("max_pool_size must be greater than or equal to min_pool_size")
        if self.connect_timeout_seconds <= 0:
            raise DatabaseConfigurationError("connect_timeout_seconds must be positive")
        if self.pool_wait_timeout_seconds <= 0:
            raise DatabaseConfigurationError("pool_wait_timeout_seconds must be positive")
        if self.max_idle_seconds <= 0:
            raise DatabaseConfigurationError("max_idle_seconds must be positive")
        if self.max_lifetime_seconds <= 0:
            raise DatabaseConfigurationError("max_lifetime_seconds must be positive")
        if self.max_waiting <= 0:
            raise DatabaseConfigurationError("max_waiting must be positive")
        if self.num_workers <= 0:
            raise DatabaseConfigurationError("num_workers must be positive")

    @classmethod
    def from_env(cls, prefix: str = "POSTGRES_") -> DatabaseConfig:
        env = os.environ
        dsn = env.get(f"{prefix}DSN")
        if dsn:
            return cls(
                dsn=dsn,
                min_pool_size=int(env.get(f"{prefix}MIN_POOL_SIZE", "1")),
                max_pool_size=int(env.get(f"{prefix}MAX_POOL_SIZE", "10")),
                connect_timeout_seconds=float(env.get(f"{prefix}CONNECT_TIMEOUT", "5")),
                pool_wait_timeout_seconds=float(env.get(f"{prefix}POOL_WAIT_TIMEOUT", "10")),
                max_idle_seconds=float(env.get(f"{prefix}MAX_IDLE_SECONDS", "300")),
                max_lifetime_seconds=float(env.get(f"{prefix}MAX_LIFETIME_SECONDS", "3600")),
                max_waiting=int(env.get(f"{prefix}MAX_WAITING", "20")),
                num_workers=int(env.get(f"{prefix}POOL_WORKERS", "3")),
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
            min_pool_size=int(env.get(f"{prefix}MIN_POOL_SIZE", "1")),
            max_pool_size=int(env.get(f"{prefix}MAX_POOL_SIZE", "10")),
            connect_timeout_seconds=float(env.get(f"{prefix}CONNECT_TIMEOUT", "5")),
            pool_wait_timeout_seconds=float(env.get(f"{prefix}POOL_WAIT_TIMEOUT", "10")),
            max_idle_seconds=float(env.get(f"{prefix}MAX_IDLE_SECONDS", "300")),
            max_lifetime_seconds=float(env.get(f"{prefix}MAX_LIFETIME_SECONDS", "3600")),
            max_waiting=int(env.get(f"{prefix}MAX_WAITING", "20")),
            num_workers=int(env.get(f"{prefix}POOL_WORKERS", "3")),
            session_statements=_read_session_statements(env, prefix),
        )


def _read_session_statements(env: os._Environ[str], prefix: str) -> tuple[str, ...]:
    raw = env.get(f"{prefix}SESSION_STATEMENTS", "")
    return tuple(statement.strip() for statement in raw.split(";") if statement.strip())
