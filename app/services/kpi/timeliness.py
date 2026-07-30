"""Срок внесения трудозатрат: до указанного времени N-го рабочего дня после дня работы."""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.production_calendar_day import ProductionCalendarDay

MAX_LOOKAHEAD_DAYS = 30


def _is_workday(db: Session, day: date) -> bool:
    """Нет записи в календаре — считаем рабочими Пн–Пт (тот же fallback, что в ресурсах)."""
    row = db.query(ProductionCalendarDay).filter(ProductionCalendarDay.date == day).first()
    if row is None:
        return day.weekday() < 5
    return bool(row.is_workday)


def deadline_for(db: Session, work_day: date, days: int, time_str: str) -> datetime:
    """Крайний момент внесения часов за ``work_day``."""
    hh, _, mm = time_str.partition(":")
    hour, minute = int(hh), int(mm or 0)
    remaining = max(1, days)
    cursor = work_day
    for _ in range(MAX_LOOKAHEAD_DAYS):
        cursor = cursor + timedelta(days=1)
        if _is_workday(db, cursor):
            remaining -= 1
            if remaining == 0:
                return datetime(cursor.year, cursor.month, cursor.day, hour, minute)
    # Календарь не дал ни одного рабочего дня — не штрафуем.
    return datetime(work_day.year, work_day.month, work_day.day, hour, minute) + timedelta(days=days)


def is_late(
    db: Session, work_day: date, created_at: Optional[datetime], days: int, time_str: str
) -> bool:
    """Запись просрочена, если внесена позже крайнего момента. Без даты внесения — не судим."""
    if created_at is None:
        return False
    return created_at > deadline_for(db, work_day, days, time_str)
