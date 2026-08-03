"""Срок внесения трудозатрат — два способа, переключаются в общих правилах.

* ``hours_from_start`` (по умолчанию, формулировка ТЗ) — запись просрочена,
  если создана позже чем через N часов после времени начала работы,
  указанного в ней. Производственный календарь не участвует, счёт
  непрерывный. В SQL дашборда заказчика это ``wl.created − wl.started >
  INTERVAL '18 hours'``.
* ``calendar`` — до указанного времени N-го рабочего дня после дня работы,
  выходные и праздники пропускаются по производственному календарю.

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
    """Способ «рабочие дни и время отсечки»: позже крайнего момента — просрочка.

    Без даты внесения не судим — вызывающий код такие записи отбрасывает
    заранее, здесь это лишь страховка.
    """
    if created_at is None:
        return False
    return created_at > deadline_for(calendar, work_day, days, time_str)


def is_late_by_hours(
    started_at: Optional[datetime], created_at: Optional[datetime], hours: int,
) -> bool:
    """Способ «часов от времени работы» (ТЗ): создана позже чем через N часов — просрочка.

    Точка отсчёта — время начала работы в самой записи, а не полночь дня
    работы: в Jira у записи о работе есть время, и ТЗ считает разницу именно
    от него («Дата создания записи в журнале работ − Дата, указанная в
    записи > 18 часов»). Пояснение старой страницы ТЗ «позднее чем 9 часов
    после завершения рабочего дня» этому не противоречит: работа начата в 9
    утра, плюс 18 часов — 3 часа ночи, ровно 9 часов после 18:00.
    """
    if created_at is None or started_at is None:
        return False
    return created_at - started_at > timedelta(hours=max(1, hours))


def is_worklog_late(
    calendar: dict[date, bool],
    started_at: Optional[datetime],
    created_at: Optional[datetime],
    settings,
) -> bool:
    """Просрочена ли запись — по способу, выбранному в общих правилах."""
    if settings.worklog_deadline_mode == "calendar":
        if started_at is None:
            return False
        return is_late(
            calendar, started_at.date(), created_at,
            settings.worklog_deadline_days, settings.worklog_deadline_time,
        )
    return is_late_by_hours(started_at, created_at, settings.worklog_deadline_hours)
