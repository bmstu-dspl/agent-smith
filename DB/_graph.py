from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._database import PostgresDatabase


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
        self._database.execute(
            """
            INSERT INTO graph_nodes (node_id, node_type, properties)
            VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (node_id) DO UPDATE
            SET node_type = EXCLUDED.node_type,
                properties = EXCLUDED.properties,
                updated_at = NOW();
            """,
            (node.node_id, node.node_type, _json(node.properties)),
        )

    def upsert_edge(self, edge: GraphEdge) -> None:
        self._database.execute(
            """
            INSERT INTO graph_edges (edge_id, from_node_id, to_node_id, edge_type, properties)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (edge_id) DO UPDATE
            SET from_node_id = EXCLUDED.from_node_id,
                to_node_id = EXCLUDED.to_node_id,
                edge_type = EXCLUDED.edge_type,
                properties = EXCLUDED.properties,
                updated_at = NOW();
            """,
            (
                edge.edge_id,
                edge.from_node_id,
                edge.to_node_id,
                edge.edge_type,
                _json(edge.properties),
            ),
        )

    def get_node(self, node_id: str) -> dict[str, object] | None:
        return self._database.fetch_one(
            """
            SELECT node_id, node_type, properties, created_at, updated_at
            FROM graph_nodes
            WHERE node_id = %s;
            """,
            (node_id,),
        )

    def get_neighbors(self, node_id: str, *, edge_type: str | None = None) -> list[dict[str, object]]:
        if edge_type is None:
            return self._database.fetch_all(
                """
                SELECT e.edge_id, e.edge_type, e.properties, n.node_id, n.node_type, n.properties AS node_properties
                FROM graph_edges AS e
                JOIN graph_nodes AS n ON n.node_id = e.to_node_id
                WHERE e.from_node_id = %s
                ORDER BY e.edge_id;
                """,
                (node_id,),
            )

        return self._database.fetch_all(
            """
            SELECT e.edge_id, e.edge_type, e.properties, n.node_id, n.node_type, n.properties AS node_properties
            FROM graph_edges AS e
            JOIN graph_nodes AS n ON n.node_id = e.to_node_id
            WHERE e.from_node_id = %s AND e.edge_type = %s
            ORDER BY e.edge_id;
            """,
            (node_id, edge_type),
        )

    def traverse(self, node_id: str, *, max_depth: int = 3) -> list[dict[str, object]]:
        return self._database.fetch_all(
            """
            WITH RECURSIVE graph_walk AS (
                SELECT
                    e.edge_id,
                    e.from_node_id,
                    e.to_node_id,
                    e.edge_type,
                    1 AS depth,
                    ARRAY[e.from_node_id, e.to_node_id]::text[] AS path
                FROM graph_edges AS e
                WHERE e.from_node_id = %s

                UNION ALL

                SELECT
                    e.edge_id,
                    e.from_node_id,
                    e.to_node_id,
                    e.edge_type,
                    gw.depth + 1 AS depth,
                    gw.path || e.to_node_id
                FROM graph_walk AS gw
                JOIN graph_edges AS e ON e.from_node_id = gw.to_node_id
                WHERE gw.depth < %s
                  AND NOT e.to_node_id = ANY(gw.path)
            )
            SELECT edge_id, from_node_id, to_node_id, edge_type, depth, path
            FROM graph_walk
            ORDER BY depth, edge_id;
            """,
            (node_id, max_depth),
        )


def _json(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=True, sort_keys=True)
