from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from DB import OrmBase


class MessageModel(OrmBase):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')", name="role_valid"),
        Index("idx_messages_session_created", "session_id", "created_at"),
        Index("idx_messages_session_active_final", "session_id", "is_active", "is_final"),
    )

    message_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # "metadata" зарезервировано в Declarative Base, поэтому атрибут metadata_, колонка metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SystemSettingModel(OrmBase):
    __tablename__ = "system_settings"

    setting_key: Mapped[str] = mapped_column(Text, primary_key=True)
    setting_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
