"""Часы за пятницу можно внести до 12:00 понедельника — выходные не считаются."""
from datetime import date, datetime, timedelta

from app.models.production_calendar_day import ProductionCalendarDay
from app.services.kpi.timeliness import MAX_LOOKAHEAD_DAYS, deadline_for, is_late, load_calendar

WEEK = {
    date(2026, 7, 24): True,   # пятница
    date(2026, 7, 25): False,  # суббота
    date(2026, 7, 26): False,  # воскресенье
    date(2026, 7, 27): True,   # понедельник
    date(2026, 7, 28): True,
}


def _seed_week(db):
    for d, workday in WEEK.items():
        db.add(ProductionCalendarDay(
            date=d, is_workday=workday,
            kind="workday" if workday else "weekend",
            hours=8.0 if workday else 0.0, source="manual",
            synced_at=datetime(2026, 7, 1),
        ))
    db.commit()


def test_load_calendar_reads_range_once(db_session):
    """Календарь читается одним запросом в словарь — без похода в БД на каждый день (ВАЖНО 6)."""
    _seed_week(db_session)
    calendar = load_calendar(db_session, date(2026, 7, 24), date(2026, 7, 28))
    assert calendar == WEEK


def test_deadline_skips_weekend():
    assert deadline_for(WEEK, date(2026, 7, 24), days=1, time_str="12:00") == \
        datetime(2026, 7, 27, 12, 0)


def test_late_detection():
    assert is_late(WEEK, date(2026, 7, 24), datetime(2026, 7, 27, 11, 0), 1, "12:00") is False
    assert is_late(WEEK, date(2026, 7, 24), datetime(2026, 7, 27, 12, 1), 1, "12:00") is True


def test_missing_day_falls_back_to_weekday_rule():
    """День вне загруженного словаря — тот же fallback Пн-Пт, что раньше давал fallback на пустой БД."""
    # 2026-07-24 пятница, следующий рабочий день по правилу Пн-Пт — понедельник 27-е.
    assert deadline_for({}, date(2026, 7, 24), days=1, time_str="12:00") == \
        datetime(2026, 7, 27, 12, 0)


def test_bad_time_string_falls_back_to_default_instead_of_raising():
    """Мелочь: кривая настройка времени отсечки не должна ронять весь отчёт."""
    assert deadline_for(WEEK, date(2026, 7, 24), days=1, time_str="не время") == \
        datetime(2026, 7, 27, 12, 0)


def test_empty_calendar_lookahead_fallback_is_lenient_not_stricter():
    """Мелочь: если календарь не даёт ни одного рабочего дня внутри окна поиска,
    дедлайн отодвигается на щедрый срок, а не сокращается до work_day + days
    (комментарий обещал «не штрафуем», код давал более строгий срок)."""
    work_day = date(2026, 7, 1)
    all_non_workdays = {work_day + timedelta(days=i): False for i in range(1, MAX_LOOKAHEAD_DAYS + 2)}
    result = deadline_for(all_non_workdays, work_day, days=1, time_str="12:00")
    assert result >= datetime.combine(work_day, datetime.min.time()) + timedelta(days=MAX_LOOKAHEAD_DAYS)
