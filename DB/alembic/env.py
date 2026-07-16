from __future__ import annotations

from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from DB import DatabaseConfig
from DB._graph_models import GraphEdgeModel, GraphNodeModel
from DB._orm import Base
from RAG._models import ChunkModel, DocumentModel, DocumentVersionModel
from memory._models import MessageModel, SystemSettingModel
_MODELS = (
    GraphNodeModel,
    GraphEdgeModel,
    DocumentModel,
    DocumentVersionModel,
    ChunkModel,
    MessageModel,       
    SystemSettingModel,
)
target_metadata = Base.metadata


def _database_url() -> str:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    database_url = DatabaseConfig.from_env().dsn
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied_connection = context.config.attributes.get("connection")
    if supplied_connection is not None:
        _configure(supplied_connection)
        return

    database_url = _database_url()
    context.config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    connectable = engine_from_config(
        context.config.get_section(context.config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _configure(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
