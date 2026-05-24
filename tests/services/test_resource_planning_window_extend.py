"""Тесты приватного хелпера `_extend_window_for_hours`.

Хелпер расширяет окно фазы вправо так, чтобы вместить заданное число часов
с учётом involvement %, выходных и аномалий производственного календаря,
не выходя за конец квартала.
"""

from datetime import date
import json

from app.models import Absence, AbsenceReason, Employee
from app.models.production_calendar_day import ProductionCalendarDay
from app.services.resource_planning_service import ResourcePlanningService


def test_extend_window_fits_in_window(db_session):
    svc = ResourcePlanningService(db_session)
    # 30h at 6 * 0.9 = 5.4h/day cap, starting Mon 20.04 -> ceil(30/5.4)=6 days.
    # 5.4 * 5 = 27h за пн..пт; на пн 27.04 остаётся 3h. Итого 6 ключей, сумма = 30.
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 4, 20),
        hours=30.0,
        involvement=0.9,
        q_end=date(2026, 6, 30),
    )
    assert end == date(2026, 4, 27)
    daily = json.loads(daily_json)
    assert abs(sum(daily.values()) - 30.0) < 0.01
    assert len(daily) == 6


def test_extend_window_grows_when_hours_exceed_cap(db_session):
    svc = ResourcePlanningService(db_session)
    # 40h at 5.4h/day -> ceil(40/5.4)=8 working days. Mon 20.04 + 7 weekday-skip = Wed 29.04.
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 4, 20),
        hours=40.0,
        involvement=0.9,
        q_end=date(2026, 6, 30),
    )
    assert end == date(2026, 4, 29)
    daily = json.loads(daily_json)
    assert abs(sum(daily.values()) - 40.0) < 0.01
    # 8 working days
    assert len(daily) == 8


def test_extend_window_clamps_to_quarter_end(db_session):
    svc = ResourcePlanningService(db_session)
    # 100h from Mon 29.06; q_end = Tue 30.06. Only 2 working days available.
    # Sum allocated = 2 * 5.4 = 10.8h (capped); last day = 30.06.
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 6, 29),
        hours=100.0,
        involvement=0.9,
        q_end=date(2026, 6, 30),
    )
    assert end == date(2026, 6, 30)
    daily = json.loads(daily_json)
    assert abs(sum(daily.values()) - 10.8) < 0.01
    assert len(daily) == 2


def test_extend_window_skips_weekend(db_session):
    svc = ResourcePlanningService(db_session)
    # Start on Friday 24.04; need 16h at 6h/day cap (involvement=1.0).
    # Fri=6, Sat=0, Sun=0, Mon=6, Tue=4 -> end = Tue 28.04. Keys = {24, 27, 28}.
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 4, 24),
        hours=16.0,
        involvement=1.0,
        q_end=date(2026, 6, 30),
    )
    assert end == date(2026, 4, 28)
    daily = json.loads(daily_json)
    assert set(daily.keys()) == {"2026-04-24", "2026-04-27", "2026-04-28"}
    assert abs(sum(daily.values()) - 16.0) < 0.01


def test_extend_window_honours_production_calendar_holiday(db_session):
    # Wed 22.04 — праздник (0h по календарю).
    db_session.add(
        ProductionCalendarDay(
            date=date(2026, 4, 22),
            hours=0.0,
            is_workday=False,
            kind="holiday",
            source="manual",
        )
    )
    db_session.commit()
    svc = ResourcePlanningService(db_session)
    # 16h, inv=1.0, cap=6/день. Mon=6, Tue=6, Wed=0 (праздник пропускается),
    # Thu=4 -> end Thu 23.04, 3 ключа с часами.
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 4, 20),
        hours=16.0,
        involvement=1.0,
        q_end=date(2026, 6, 30),
    )
    assert end == date(2026, 4, 23)
    daily = json.loads(daily_json)
    assert "2026-04-22" not in daily  # holiday skipped
    assert set(daily.keys()) == {"2026-04-20", "2026-04-21", "2026-04-23"}
    assert abs(sum(daily.values()) - 16.0) < 0.01


def test_extend_window_skips_employee_absence(db_session):
    """Дни отпуска конкретного сотрудника пропускаются как выходные.

    Без передачи `employee_id` хелпер раскладывает часы строго по
    производственному календарю — отпуск Фокеевой 08-10.06 получал план=0
    (через `build_availability`), но scheduler через `_extend_window_for_hours`
    клал туда часы → перегруз 5600%.
    """
    reason = AbsenceReason(
        code="vacation", label="Отпуск", is_planned=True, is_active=True
    )
    db_session.add(reason)
    emp = Employee(
        jira_account_id="acc-extend-abs",
        display_name="Vacationer",
        is_active=True,
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(
        Absence(
            employee_id=emp.id,
            start_date=date(2026, 6, 8),
            end_date=date(2026, 6, 10),
            reason_id=reason.id,
        )
    )
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    # 40h от Mon 01.06.2026, involvement=1.0 (cap 6h/день). Без отпуска:
    # 01-05.06 (Пн-Пт) = 30h, 06-07 выходные, 08-10 — 10h → end 10.06 (7 ключей).
    # С отпуском 08-10.06: 01-05.06 = 30h, далее пропускаем 06-10.06, 11-12.06
    # (Чт-Пт) = 12h. На 11.06 уместится 6h, на 12.06 — 4h → end 12.06, 7 ключей.
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 6, 1),
        hours=40.0,
        involvement=1.0,
        q_end=date(2026, 6, 30),
        employee_id=emp.id,
    )
    daily = json.loads(daily_json)
    # Дни отпуска НЕ должны попасть в раскладку.
    for iso in ("2026-06-08", "2026-06-09", "2026-06-10"):
        assert iso not in daily, f"{iso} — отпуск, не должно быть в daily_hours"
    # Все часы разложены, окно расширено за отпуск.
    assert abs(sum(daily.values()) - 40.0) < 0.01
    assert end == date(2026, 6, 12)
    assert "2026-06-12" in daily


def test_extend_window_without_employee_ignores_absences(db_session):
    """Backward compat: вызов без `employee_id` НЕ грузит отсутствия и
    раскладывает часы по производственному календарю, как раньше."""
    reason = AbsenceReason(
        code="vacation", label="Отпуск", is_planned=True, is_active=True
    )
    db_session.add(reason)
    emp = Employee(
        jira_account_id="acc-no-emp-id",
        display_name="X",
        is_active=True,
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(
        Absence(
            employee_id=emp.id,
            start_date=date(2026, 6, 8),
            end_date=date(2026, 6, 10),
            reason_id=reason.id,
        )
    )
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    end, daily_json = svc._extend_window_for_hours(
        start_date=date(2026, 6, 1),
        hours=40.0,
        involvement=1.0,
        q_end=date(2026, 6, 30),
    )
    daily = json.loads(daily_json)
    # employee_id не передан → отсутствия игнорируются, дни 08-09.06 в раскладке
    # (01-05 = 30h, 06-07 выходные, 08.06 = 6h, 09.06 = 4h → end 09.06).
    assert "2026-06-08" in daily
    assert abs(sum(daily.values()) - 40.0) < 0.01
    assert end == date(2026, 6, 9)
