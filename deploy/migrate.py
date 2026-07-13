from __future__ import annotations

import logging

from DB import DatabaseConfig, Migrator, PostgresDatabase


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    database = PostgresDatabase(DatabaseConfig.from_env())
    try:
        database.open()
        applied = database.apply_migrations(Migrator().load())
        logging.info("database migrations complete; applied=%s", applied)
    finally:
        database.close()


if __name__ == "__main__":
    main()
