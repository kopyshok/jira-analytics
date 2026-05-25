"""FeedbackItem — пользовательские баг-репорты и предложения улучшений."""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class FeedbackKind(str, PyEnum):
    bug = "bug"
    idea = "idea"


class FeedbackItem(Base, TimestampMixin):
    __tablename__ = "feedback_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    kind: Mapped[FeedbackKind] = mapped_column(
        Enum(FeedbackKind, native_enum=False), nullable=False
    )
    author_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    page_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    # bug-only (nullable for ideas):
    steps_to_reproduce: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_feedback_kind_read_created", "kind", "read_at", "created_at"),
    )
