"""ReleaseNote — запись в ленте «Что нового»."""
from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

NOTE_TYPES = ("new", "improvement", "fix")
SECTIONS = (
    "scenarios", "resources", "analytics", "issues",
    "dashboard", "backlog", "sync", "settings", "general",
)


class ReleaseNote(Base, TimestampMixin):
    __tablename__ = "release_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    note_type: Mapped[str] = mapped_column(String(20), nullable=False)
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    help_link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
