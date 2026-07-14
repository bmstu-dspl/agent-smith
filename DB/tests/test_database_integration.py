from __future__ import annotations

import os
from pathlib import Path
from unittest import TestCase
from uuid import uuid4

from dotenv import dotenv_values

from sqlalchemy import Integer, String, select
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from DB import DatabaseConfig, GraphEdge, GraphNode, GraphStore, Migrator, PostgresDatabase


class TestBase(DeclarativeBase):
    pass


class IntegrationNoteModel(TestBase):
    __tablename__ = "integration_notes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    body: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PostgresDatabaseIntegrationTestCase(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._env_path = Path(__file__).resolve().parents[2] / ".env"
        cls._env = {
            key: value
            for key, value in dotenv_values(cls._env_path).items()
            if value is not None
        }
        cls._schema = f"test_db_{uuid4().hex[:12]}"
        cls._database = PostgresDatabase(
            DatabaseConfig(
                dsn=_dsn_from_env(cls._env),
                pool_size=4,
                max_overflow=0,
                session_statements=(f"SET search_path TO {cls._schema}, public",),
            )
        )
        cls._database.open()
        with cls._database.engine.begin() as connection:
            connection.execute(CreateSchema(cls._schema))
        cls._database.migrate()
        IntegrationNoteModel.__table__.create(cls._database.engine)
        cls._graph = GraphStore(cls._database)

    @classmethod
    def tearDownClass(cls) -> None:
        with cls._database.engine.begin() as connection:
            connection.execute(DropSchema(cls._schema, cascade=True, if_exists=True))
        cls._database.close()

    def test_healthcheck(self) -> None:
        health = self._database.healthcheck()
        self.assertIn("database_name", health)
        self.assertEqual(health["schema_name"], self._schema)

    def test_alembic_revision_is_current(self) -> None:
        self.assertTrue(Migrator(self._database).is_current())

    def test_orm_session_roundtrip(self) -> None:
        with self._database.session() as session:
            session.add(IntegrationNoteModel(id="note-1", body="first note", priority=3))

        with self._database.session() as session:
            note = session.get(IntegrationNoteModel, "note-1")
            self.assertIsNotNone(note)
            assert note is not None
            self.assertEqual((note.body, note.priority), ("first note", 3))

    def test_orm_select(self) -> None:
        with self._database.session() as session:
            session.add_all(
                [
                    IntegrationNoteModel(id="note-2", body="second note"),
                    IntegrationNoteModel(id="note-3", body="third note"),
                ]
            )

        with self._database.session() as session:
            notes = session.scalars(
                select(IntegrationNoteModel)
                .where(IntegrationNoteModel.id.in_(["note-2", "note-3"]))
                .order_by(IntegrationNoteModel.id)
            ).all()
        self.assertEqual([(note.id, note.body) for note in notes], [("note-2", "second note"), ("note-3", "third note")])

    def test_transaction_rolls_back_on_error(self) -> None:
        with self.assertRaises(RuntimeError):
            with self._database.session() as session:
                session.add(IntegrationNoteModel(id="note-rollback", body="should disappear"))
                raise RuntimeError("boom")

        with self._database.session() as session:
            self.assertIsNone(session.get(IntegrationNoteModel, "note-rollback"))

    def test_graph_store_roundtrip_and_traversal(self) -> None:
        self._graph.upsert_node(GraphNode(node_id="user-1", node_type="user", properties={"name": "Alice"}))
        self._graph.upsert_node(GraphNode(node_id="project-1", node_type="project", properties={"name": "Smith"}))
        self._graph.upsert_node(GraphNode(node_id="doc-1", node_type="document", properties={"title": "Spec"}))
        self._graph.upsert_edge(
            GraphEdge(
                edge_id="edge-1",
                from_node_id="user-1",
                to_node_id="project-1",
                edge_type="owns",
                properties={"role": "owner"},
            )
        )
        self._graph.upsert_edge(
            GraphEdge(
                edge_id="edge-2",
                from_node_id="project-1",
                to_node_id="doc-1",
                edge_type="contains",
                properties={},
            )
        )

        node = self._graph.get_node("user-1")
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node["properties"]["name"], "Alice")

        neighbors = self._graph.get_neighbors("user-1")
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0]["node_id"], "project-1")

        traversal = self._graph.traverse("user-1", max_depth=3)
        self.assertEqual([row["to_node_id"] for row in traversal], ["project-1", "doc-1"])


def _dsn_from_env(env: dict[str, str]) -> str:
    direct_dsn = os.environ.get("DB_TEST_POSTGRES_DSN")
    if direct_dsn:
        return direct_dsn

    for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PORT"):
        if not env.get(key):
            raise ValueError(f"missing {key} in .env")

    host = os.environ.get("DB_TEST_POSTGRES_HOST") or os.environ.get("POSTGRES_HOST") or "127.0.0.1"
    port = os.environ.get("DB_TEST_POSTGRES_PORT") or env["POSTGRES_PORT"]
    user = os.environ.get("DB_TEST_POSTGRES_USER") or env["POSTGRES_USER"]
    password = os.environ.get("DB_TEST_POSTGRES_PASSWORD") or env["POSTGRES_PASSWORD"]
    database = os.environ.get("DB_TEST_POSTGRES_DB") or env["POSTGRES_DB"]
    return (
        f"postgresql://{user}:{password}"
        f"@{host}:{port}/{database}"
    )
