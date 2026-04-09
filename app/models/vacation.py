"""Vacation model - employee time-off periods."""

from datetime import date
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.employee import Employee


class Vacation(Base, TimestampMixin):
    """Запись об отпуске сотрудника.

    Источник вычета capacity при квартальном планировании.
    Заполняется вручную.
    """

    __tablename__ = "vacations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    hours_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    employee: Mapped["Employee"] = relationship(back_populates="vacations")

    def __repr__(self) -> str:
        return f"<Vacation {self.start_date} - {self.end_date}>"
