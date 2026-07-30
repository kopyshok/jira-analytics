"""Часы за пятницу можно внести до 12:00 понедельника — выходные не считаются."""
from datetime import date, datetime

from app.models.production_calendar_day import ProductionCalendarDay
from app.services.kpi.timeliness import deadline_for, is_late


def _seed_week(db):
    days = {
        date(2026, 7, 24): True,   # пятница
        date(2026, 7, 25): False,  # суббота
        date(2026, 7, 26): False,  # воскресенье
        date(2026, 7, 27): True,   # понедельник
        date(2026, 7, 28): True,
    }
    for d, workday in days.items():
        db.add(ProductionCalendarDay(
            date=d, is_workday=workday,
            kind="workday" if workday else "weekend",
            hours=8.0 if workday else 0.0, source="manual",
            synced_at=datetime(2026, 7, 1),
        ))
    db.commit()


def test_deadline_skips_weekend(db_session):
    _seed_week(db_session)
    assert deadline_for(db_session, date(2026, 7, 24), days=1, time_str="12:00") == \
        datetime(2026, 7, 27, 12, 0)


def test_late_detection(db_session):
    _seed_week(db_session)
    assert is_late(db_session, date(2026, 7, 24), datetime(2026, 7, 27, 11, 0), 1, "12:00") is False
    assert is_late(db_session, date(2026, 7, 24), datetime(2026, 7, 27, 12, 1), 1, "12:00") is True
