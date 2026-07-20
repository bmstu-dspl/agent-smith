from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from DB import OrmBase


class McpServerModel(OrmBase):
    __tablename__ = "mcp_servers"
    __table_args__ = (
        CheckConstraint("transport_type IN ('sse', 'stdio', 'http')", name="ck_mcp_servers_transport_type_valid"),
        Index("idx_mcp_servers_is_active", "is_active"),
    )

    server_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    transport_type: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    # Зашифрованные строки — см. mcp_registry/_crypto.py.
    # _encrypted — явный сигнал в коде, что сюда нельзя писать plain dict.
    headers_encrypted: Mapped[str | None] = mapped_column(Text)
    query_params_encrypted: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
