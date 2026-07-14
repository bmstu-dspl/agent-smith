from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import any_, func, literal, select
from sqlalchemy.dialects.postgresql import array, insert

from ._database import PostgresDatabase
from ._graph_models import GraphEdgeModel, GraphNodeModel


@dataclass(slots=True, frozen=True)
class GraphNode:
    node_id: str
    node_type: str
    properties: dict[str, Any]


@dataclass(slots=True, frozen=True)
class GraphEdge:
    edge_id: str
    from_node_id: str
    to_node_id: str
    edge_type: str
    properties: dict[str, Any]


class GraphStore:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def upsert_node(self, node: GraphNode) -> None:
        statement = insert(GraphNodeModel).values(
            node_id=node.node_id,
            node_type=node.node_type,
            properties=node.properties,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[GraphNodeModel.node_id],
            set_={
                "node_type": statement.excluded.node_type,
                "properties": statement.excluded.properties,
                "updated_at": func.now(),
            },
        )
        with self._database.session() as session:
            session.execute(statement)

    def upsert_edge(self, edge: GraphEdge) -> None:
        statement = insert(GraphEdgeModel).values(
            edge_id=edge.edge_id,
            from_node_id=edge.from_node_id,
            to_node_id=edge.to_node_id,
            edge_type=edge.edge_type,
            properties=edge.properties,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[GraphEdgeModel.edge_id],
            set_={
                "from_node_id": statement.excluded.from_node_id,
                "to_node_id": statement.excluded.to_node_id,
                "edge_type": statement.excluded.edge_type,
                "properties": statement.excluded.properties,
                "updated_at": func.now(),
            },
        )
        with self._database.session() as session:
            session.execute(statement)

    def get_node(self, node_id: str) -> dict[str, object] | None:
        with self._database.session() as session:
            model = session.get(GraphNodeModel, node_id)
            if model is None:
                return None
            return {
                "node_id": model.node_id,
                "node_type": model.node_type,
                "properties": model.properties,
                "created_at": model.created_at,
                "updated_at": model.updated_at,
            }

    def get_neighbors(self, node_id: str, *, edge_type: str | None = None) -> list[dict[str, object]]:
        statement = (
            select(
                GraphEdgeModel.edge_id,
                GraphEdgeModel.edge_type,
                GraphEdgeModel.properties,
                GraphNodeModel.node_id,
                GraphNodeModel.node_type,
                GraphNodeModel.properties.label("node_properties"),
            )
            .join(GraphNodeModel, GraphNodeModel.node_id == GraphEdgeModel.to_node_id)
            .where(GraphEdgeModel.from_node_id == node_id)
            .order_by(GraphEdgeModel.edge_id)
        )
        if edge_type is not None:
            statement = statement.where(GraphEdgeModel.edge_type == edge_type)
        with self._database.session() as session:
            return [dict(row) for row in session.execute(statement).mappings()]

    def traverse(self, node_id: str, *, max_depth: int = 3) -> list[dict[str, object]]:
        initial = select(
            GraphEdgeModel.edge_id,
            GraphEdgeModel.from_node_id,
            GraphEdgeModel.to_node_id,
            GraphEdgeModel.edge_type,
            literal(1).label("depth"),
            array([GraphEdgeModel.from_node_id, GraphEdgeModel.to_node_id]).label("path"),
        ).where(GraphEdgeModel.from_node_id == node_id)
        graph_walk = initial.cte("graph_walk", recursive=True)
        recursive = (
            select(
                GraphEdgeModel.edge_id,
                GraphEdgeModel.from_node_id,
                GraphEdgeModel.to_node_id,
                GraphEdgeModel.edge_type,
                (graph_walk.c.depth + 1).label("depth"),
                func.array_append(graph_walk.c.path, GraphEdgeModel.to_node_id).label("path"),
            )
            .join(graph_walk, GraphEdgeModel.from_node_id == graph_walk.c.to_node_id)
            .where(
                graph_walk.c.depth < max_depth,
                GraphEdgeModel.to_node_id != any_(graph_walk.c.path),
            )
        )
        graph_walk = graph_walk.union_all(recursive)
        statement = select(graph_walk).order_by(graph_walk.c.depth, graph_walk.c.edge_id)
        with self._database.session() as session:
            return [dict(row) for row in session.execute(statement).mappings()]
