"""UsageEvent — raw события трекинга использования (хранятся 90 дней)."""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class UsageEventType(str, PyEnum):
    page_view = "page_view"
    heartbeat = "heartbeat"
    action = "action"


class UsageEvent(Base, TimestampMixin):
    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    event_type: Mapped[UsageEventType] = mapped_column(
        Enum(UsageEventType, native_enum=False), nullable=False
    )
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    action_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index("ix_usage_events_user_at", "user_id", "at"),
        Index("ix_usage_events_at_type", "at", "event_type"),
        Index("ix_usage_events_path_at", "path", "at"),
    )
