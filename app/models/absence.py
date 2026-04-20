"""Absence model — employee time-off periods."""

from datetime import date
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.absence_reason import AbsenceReason
    from app.models.employee import Employee


class Absence(Base, TimestampMixin):
    """Запись об отсутствии сотрудника.

    Источник вычета capacity при квартальном планировании. ``reason_id`` ссылается
    на редактируемый справочник ``absence_reasons``.
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
    reason_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("absence_reasons.id"), nullable=False, index=True
    )
    hours_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="absences")
    reason: Mapped["AbsenceReason"] = relationship()

    def __repr__(self) -> str:
        return f"<Absence reason_id={self.reason_id} {self.start_date} — {self.end_date}>"
