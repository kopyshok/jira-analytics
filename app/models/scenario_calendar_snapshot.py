"""ScenarioCalendarSnapshot — производственный календарь квартала на момент утверждения.

Per-day копия production_calendar_day за период квартала сценария — позволяет
точно реконструировать расчёт capacity если живой календарь правился задним числом.
"""
from datetime import date as _date
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision


class ScenarioCalendarSnapshot(Base, TimestampMixin):
    __tablename__ = "scenario_calendar_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    date: Mapped[_date] = mapped_column(Date, nullable=False)
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    is_workday: Mapped[bool] = mapped_column(Boolean, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="calendar_snapshots")
