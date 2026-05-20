"""Тесты приватного хелпера `_extend_window_for_hours`.

Хелпер расширяет окно фазы вправо так, чтобы вместить заданное число часов
с учётом involvement %, выходных и аномалий производственного календаря,
не выходя за конец квартала.
"""

from datetime import date
import json

from app.services.resource_planning_service import ResourcePlanningService


def test_extend_window_fits_in_window(db_session):
    svc = ResourcePlanningService(db_session)
    # 30h at 8 * 0.9 = 7.2h/day cap, starting Mon 20.04 -> need ceil(30/7.2)=5 days
    # Sum should equal exactly 30h.
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 4, 20),
        hours=30.0,
        involvement=0.9,
        q_end=date(2026, 6, 30),
    )
    assert end == date(2026, 4, 24)  # Mon..Fri
    daily = json.loads(daily_json)
    assert abs(sum(daily.values()) - 30.0) < 0.01
    assert len(daily) == 5


def test_extend_window_grows_when_hours_exceed_cap(db_session):
    svc = ResourcePlanningService(db_session)
    # 40h at 7.2h/day = ceil(40/7.2)=6 working days. Mon 20.04 + 5wd skipping
    # Sat 25/Sun 26 -> end is Mon 27.04.
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 4, 20),
        hours=40.0,
        involvement=0.9,
        q_end=date(2026, 6, 30),
    )
    assert end == date(2026, 4, 27)
    daily = json.loads(daily_json)
    assert abs(sum(daily.values()) - 40.0) < 0.01
    # 6 working days
    assert len(daily) == 6


def test_extend_window_clamps_to_quarter_end(db_session):
    svc = ResourcePlanningService(db_session)
    # 100h from Mon 29.06; q_end = Tue 30.06. Only 2 working days available.
    # Sum allocated = 14.4h (capped); last day = 30.06.
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 6, 29),
        hours=100.0,
        involvement=0.9,
        q_end=date(2026, 6, 30),
    )
    assert end == date(2026, 6, 30)
    daily = json.loads(daily_json)
    assert abs(sum(daily.values()) - 14.4) < 0.01
    assert len(daily) == 2


def test_extend_window_skips_weekend(db_session):
    svc = ResourcePlanningService(db_session)
    # Start on Friday 24.04; need 16h at 8h/day cap (involvement=1.0).
    # Fri=8, Sat=0, Sun=0, Mon=8 -> end = Mon 27.04.
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 4, 24),
        hours=16.0,
        involvement=1.0,
        q_end=date(2026, 6, 30),
    )
    assert end == date(2026, 4, 27)
    daily = json.loads(daily_json)
    assert set(daily.keys()) == {"2026-04-24", "2026-04-27"}
    assert abs(sum(daily.values()) - 16.0) < 0.01
