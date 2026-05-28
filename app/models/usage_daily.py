"""UsageDaily — дневной агрегат usage_events (хранится навсегда)."""
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class UsageDaily(Base, TimestampMixin):
    __tablename__ = "usage_daily"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actions_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    __table_args__ = (
        UniqueConstraint("date", "user_id", "path", name="uq_usage_daily_date_user_path"),
        Index("ix_usage_daily_date_user", "date", "user_id"),
        Index("ix_usage_daily_date_path", "date", "path"),
    )
