"""Theme — dictionary entry per work type for thematic reports."""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class Theme(Base, TimestampMixin):
    __tablename__ = "themes"
    __table_args__ = (UniqueConstraint("work_type_id", "name", name="uq_themes_work_type_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    work_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandatory_work_types.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#00c9c8")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    embedding_model_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    embedding_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    aliases_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    @property
    def aliases(self) -> list[str]:
        if not self.aliases_json:
            return []
        try:
            v = json.loads(self.aliases_json)
            return [str(x) for x in v if isinstance(x, str) and x.strip()]
        except (json.JSONDecodeError, TypeError):
            return []

    @aliases.setter
    def aliases(self, value: Optional[list[str]]) -> None:
        if not value:
            self.aliases_json = None
            return
        cleaned: list[str] = []
        seen: set[str] = set()
        for s in value:
            if not isinstance(s, str):
                continue
            t = s.strip()
            key = t.lower()
            if not t or key in seen:
                continue
            seen.add(key)
            cleaned.append(t)
        self.aliases_json = json.dumps(cleaned, ensure_ascii=False) if cleaned else None

    def __repr__(self) -> str:
        return f"<Theme {self.name} (wt={self.work_type_id})>"
