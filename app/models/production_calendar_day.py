"""Модель особых дней российского производственного календаря.

Хранит только аномалии: праздники, перенесённые рабочие дни и сокращённые дни.
Обычные будни (weekday < 5) и обычные выходные без правок в таблицу не
кладутся — для них сервис возвращает дефолт.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductionCalendarDay(Base):
    """Особый день производственного календаря РФ.

    kind: 'holiday' | 'workday' (перенос) | 'short' (сокращённый).
    source: 'xmlcalendar' | 'manual'.
    """

    __tablename__ = "production_calendar_day"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    is_workday: Mapped[bool] = mapped_column(Boolean, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="xmlcalendar"
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self) -> str:
        return f"<ProductionCalendarDay {self.date} {self.kind} workday={self.is_workday}>"
