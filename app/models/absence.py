"""Absence model - employee time-off periods (vacation / sick / day-off / other)."""

from datetime import date
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.employee import Employee


ABSENCE_REASONS = ("vacation", "sick", "day_off", "other")


class Absence(Base, TimestampMixin):
    """Запись об отсутствии сотрудника.

    Источник вычета capacity при квартальном планировании.
    Все reason'ы обрабатываются одинаково в расчёте часов.
    """

    __tablename__ = "absences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False, default="vacation")
    hours_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="absences")

    def __repr__(self) -> str:
        return f"<Absence {self.reason} {self.start_date} — {self.end_date}>"
