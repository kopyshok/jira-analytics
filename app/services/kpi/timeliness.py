"""Срок внесения трудозатрат: до указанного времени N-го рабочего дня после дня работы.

Календарь читается в словарь ОДНИМ запросом (``load_calendar``) и передаётся
в чистые функции ниже — раньше на каждый проверяемый день был отдельный
запрос к БД, а на команду в 20 человек это давало 1000+ запросов на один
месячный отчёт (см. ревью Фазы 3, ВАЖНО 6).
"""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.production_calendar_day import ProductionCalendarDay

MAX_LOOKAHEAD_DAYS = 30
DEFAULT_TIME_STR = "12:00"


def load_calendar(db: Session, start: date, end: date) -> dict[date, bool]:
    """Прочитать производственный календарь на диапазон одним запросом.

    Вызывающий код обязан брать диапазон с запасом (неделя вперёд от конца
    периода — дедлайну нужно место для поиска ближайшего рабочего дня).
    """
    rows = (
        db.query(ProductionCalendarDay)
        .filter(ProductionCalendarDay.date >= start, ProductionCalendarDay.date <= end)
        .all()
    )
    return {row.date: bool(row.is_workday) for row in rows}


def _is_workday(calendar: dict[date, bool], day: date) -> bool:
    """Нет записи в календаре — считаем рабочими Пн–Пт (тот же fallback, что в ресурсах)."""
    if day in calendar:
        return calendar[day]
    return day.weekday() < 5


def _parse_time(time_str: str) -> tuple[int, int]:
    """Разобрать «ЧЧ:ММ»; кривая настройка не должна ронять весь отчёт — берём дефолт."""
    try:
        hh, _, mm = time_str.partition(":")
        hour, minute = int(hh), int(mm or 0)
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
        return hour, minute
    except (ValueError, TypeError):
        return _parse_time(DEFAULT_TIME_STR)


def deadline_for(calendar: dict[date, bool], work_day: date, days: int, time_str: str) -> datetime:
    """Крайний момент внесения часов за ``work_day``."""
    hour, minute = _parse_time(time_str)
    remaining = max(1, days)
    cursor = work_day
    for _ in range(MAX_LOOKAHEAD_DAYS):
        cursor = cursor + timedelta(days=1)
        if _is_workday(calendar, cursor):
            remaining -= 1
            if remaining == 0:
                return datetime(cursor.year, cursor.month, cursor.day, hour, minute)
    # Календарь не дал ни одного рабочего дня во всём окне поиска — не
    # штрафуем: отодвигаем дедлайн за пределы уже просканированных
    # MAX_LOOKAHEAD_DAYS дней, а не сокращаем его до work_day + days (это
    # было бы строже уже пройденного поиска, вопреки смыслу "не штрафуем").
    return datetime(work_day.year, work_day.month, work_day.day, hour, minute) \
        + timedelta(days=MAX_LOOKAHEAD_DAYS + days)


def is_late(
    calendar: dict[date, bool], work_day: date, created_at: Optional[datetime],
    days: int, time_str: str,
) -> bool:
    """Запись просрочена, если внесена позже крайнего момента. Без даты внесения — не судим."""
    if created_at is None:
        return False
    return created_at > deadline_for(calendar, work_day, days, time_str)
