from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._errors import MigrationError


@dataclass(slots=True, frozen=True)
class Migration:
    version: str
    name: str
    sql: str


class Migrator:
    def __init__(self, migrations_path: Path | None = None) -> None:
        self._migrations_path = migrations_path or Path(__file__).resolve().parent / "migrations"

    def load(self) -> list[Migration]:
        if not self._migrations_path.exists():
            return []

        migrations: list[Migration] = []
        for path in sorted(self._migrations_path.glob("*.sql")):
            stem = path.stem
            if "_" not in stem:
                raise MigrationError(f"invalid migration file name: {path.name}")
            version, name = stem.split("_", 1)
            migrations.append(Migration(version=version, name=name, sql=path.read_text(encoding="utf-8")))
        return migrations
