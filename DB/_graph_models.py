from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ._orm import Base


class GraphNodeModel(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (Index("idx_graph_nodes_type", "node_type"),)

    node_id: Mapped[str] = mapped_column(Text, primary_key=True)
    node_type: Mapped[str] = mapped_column(Text, nullable=False)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GraphEdgeModel(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (
        Index("idx_graph_edges_from_node", "from_node_id"),
        Index("idx_graph_edges_to_node", "to_node_id"),
        Index("idx_graph_edges_type", "edge_type"),
    )

    edge_id: Mapped[str] = mapped_column(Text, primary_key=True)
    from_node_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("graph_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
    )
    to_node_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("graph_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
    )
    edge_type: Mapped[str] = mapped_column(Text, nullable=False)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
