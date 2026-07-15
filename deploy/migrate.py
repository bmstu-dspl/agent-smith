from __future__ import annotations

import logging

from DB import DatabaseConfig, PostgresDatabase


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    database = PostgresDatabase(DatabaseConfig.from_env())
    try:
        database.open()
        database.migrate()
        logging.info("database migrations complete")
    finally:
        database.close()


if __name__ == "__main__":
    main()
