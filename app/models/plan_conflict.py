"""PlanConflict — persistent объект конфликта для conflict register."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.resource_plan import ResourcePlan


class PlanConflict(Base, TimestampMixin):
    """Конфликт плана с persistent статусом.

    type: OVERLOAD_LIGHT | OVERLOAD_MED | OVERLOAD_HIGH | QUARTER_OVERFLOW |
          NO_ANALYST | NO_DEV | SPLIT_REQUIRED | LATE_START | LEVELING_DELAY | LEVELING_REASSIGN
    severity: critical | warning | info
    status: open | acknowledged | muted | resolved
    """

    __tablename__ = "plan_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resource_plans.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open",
    )
    backlog_item_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    employee_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    assignment_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    window_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    metric_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detection_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
    )

    plan: Mapped["ResourcePlan"] = relationship(back_populates="conflicts")
