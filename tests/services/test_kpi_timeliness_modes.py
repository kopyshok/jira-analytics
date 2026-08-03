"""Два способа расчёта срока внесения трудозатрат.

Способ по ТЗ («часов от времени работы») стал способом по умолчанию —
проверяется и он, и то, что старый календарный способ продолжает работать.
"""
from datetime import date, datetime

from app.services.kpi.settings import KpiSettings
from app.services.kpi.timeliness import is_late_by_hours, is_worklog_late


def test_hours_from_start_counts_from_time_in_the_record():
    """18 часов считаются от времени начала работы, а не от полуночи дня."""
    started = datetime(2026, 7, 24, 9, 0)  # пятница, 9 утра
    # Ровно 18 часов — 03:00 субботы, ещё не просрочка.
    assert is_late_by_hours(started, datetime(2026, 7, 25, 3, 0), 18) is False
    # Минутой позже — просрочка.
    assert is_late_by_hours(started, datetime(2026, 7, 25, 3, 1), 18) is True


def test_hours_from_start_does_not_forgive_weekend():
    """Способ по ТЗ не знает про выходные — в этом его отличие от календарного."""
    started = datetime(2026, 7, 24, 10, 0)  # пятница
    created = datetime(2026, 7, 27, 11, 0)  # понедельник
    settings = KpiSettings(worklog_deadline_mode="hours_from_start", worklog_deadline_hours=18)
    assert is_worklog_late({}, started, created, settings) is True

    # Календарный способ ту же запись считает внесённой вовремя: суббота и
    # воскресенье пропускаются, дедлайн — понедельник 12:00.
    calendar = {date(2026, 7, 25): False, date(2026, 7, 26): False, date(2026, 7, 27): True}
    settings = KpiSettings(worklog_deadline_mode="calendar", worklog_deadline_days=1,
                           worklog_deadline_time="12:00")
    assert is_worklog_late(calendar, started, created, settings) is False


def test_record_without_created_at_is_not_judged():
    """Без даты внесения судить нечего — ни один способ не помечает запись просроченной."""
    for mode in ("hours_from_start", "calendar"):
        settings = KpiSettings(worklog_deadline_mode=mode)
        assert is_worklog_late({}, datetime(2026, 7, 24, 9, 0), None, settings) is False


def test_default_mode_is_the_one_from_the_spec():
    assert KpiSettings().worklog_deadline_mode == "hours_from_start"
    assert KpiSettings().worklog_deadline_hours == 18
