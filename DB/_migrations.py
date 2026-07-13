from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from ._errors import MigrationError

if TYPE_CHECKING:
    from ._database import PostgresDatabase


class Migrator:
    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self._database = database
        self._config = _alembic_config()

    def upgrade(self, revision: str = "head") -> None:
        if self._database is None:
            raise MigrationError("database is required to apply Alembic migrations")
        try:
            with self._database.engine.begin() as connection:
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(:namespace, :resource)"),
                    {"namespace": 0x524147, "resource": 0x4D494752},
                )
                self._config.attributes["connection"] = connection
                command.upgrade(self._config, revision)
        except Exception as error:
            if isinstance(error, MigrationError):
                raise
            raise MigrationError(f"failed to apply Alembic revision {revision}") from error
        finally:
            self._config.attributes.pop("connection", None)

    def is_current(self) -> bool:
        if self._database is None:
            raise MigrationError("database is required to inspect Alembic migrations")
        scripts = ScriptDirectory.from_config(self._config)
        with self._database.engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_heads()
        return set(current) == set(scripts.get_heads())


def _alembic_config() -> Config:
    package_path = Path(__file__).resolve().parent
    config = Config()
    config.set_main_option("script_location", str(package_path / "alembic"))
    config.set_main_option("prepend_sys_path", str(package_path.parent))
    config.set_main_option("path_separator", "os")
    return config
