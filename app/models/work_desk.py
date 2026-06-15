"""Рабочий стол аналитика — публичная страница-монитор по токену."""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class WorkDesk(Base, TimestampMixin):
    __tablename__ = "work_desks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    enabled_widgets_raw: Mapped[str] = mapped_column(
        "enabled_widgets", Text, nullable=False, default="[]", server_default="[]"
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    employee = relationship("Employee")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @property
    def enabled_widgets(self) -> list[str]:
        try:
            return json.loads(self.enabled_widgets_raw or "[]")
        except (TypeError, ValueError):
            return []

    @enabled_widgets.setter
    def enabled_widgets(self, value: list[str]) -> None:
        self.enabled_widgets_raw = json.dumps(list(value or []))
