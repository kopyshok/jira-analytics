"""Тесты формулы дневной ёмкости с учётом коэф вовлечённости."""

import pytest
from datetime import date, timedelta
from app.services.resource_planning_service import ResourcePlanningService


def test_daily_capacity_with_involvement(db_session):
    """8 ч × 0.7 = 5.6 ч/день."""
    svc = ResourcePlanningService(db_session)
    cap = svc._daily_role_capacity(avail_hours=8.0, involvement=0.7, parallel_count=1)
    assert cap == pytest.approx(5.6, abs=0.01)


def test_daily_capacity_parallel(db_session):
    """Два параллельных исполнителя × 100% вовлечённость = 16 ч/день."""
    svc = ResourcePlanningService(db_session)
    cap = svc._daily_role_capacity(avail_hours=8.0, involvement=1.0, parallel_count=2)
    assert cap == 16.0


def test_daily_capacity_null_involvement_uses_full_avail(db_session):
    """involvement=None → не урезаем ёмкость (legacy для задач без Jira-данных)."""
    svc = ResourcePlanningService(db_session)
    cap = svc._daily_role_capacity(avail_hours=8.0, involvement=None, parallel_count=1)
    assert cap == 8.0


def test_daily_capacity_clamps_invalid_involvement(db_session):
    """involvement < 0 → 0; involvement > 1 → 1."""
    svc = ResourcePlanningService(db_session)
    assert svc._daily_role_capacity(8.0, -0.1, 1) == 0.0
    assert svc._daily_role_capacity(8.0, 1.5, 1) == 8.0


def test_allocate_hours_respects_daily_capacity(db_session):
    """20 hours, daily_capacity=5.6 → ровно 4 рабочих дня; в каждый день записано <=5.6 ч."""
    svc = ResourcePlanningService(db_session)
    # Build a remaining map: 10 weekdays of 8h each
    start = date(2026, 5, 4)  # Monday
    days = [start + timedelta(days=i) for i in range(14) if (start + timedelta(days=i)).weekday() < 5]
    remaining = {"emp-1": {d: 8.0 for d in days}}

    segments = svc._allocate_hours(
        employee_id="emp-1",
        total_hours=20.0,
        earliest_start=start,
        deadline=start + timedelta(days=20),
        remaining=remaining,
        daily_capacity=5.6,
    )
    assert len(segments) == 1  # single bar
    seg_start, seg_end, seg_hours, _ = segments[0]
    assert seg_hours == pytest.approx(20.0, abs=0.01)
    # Verify per-day burn never exceeded daily_capacity
    burnt = {d: 8.0 - remaining["emp-1"][d] for d in days}
    for h in burnt.values():
        assert h <= 5.6 + 0.01, f"per-day burn {h} exceeds cap 5.6"
    # Number of days with non-zero burn ≈ ceil(20 / 5.6) = 4
    nonzero = sum(1 for h in burnt.values() if h > 0)
    assert nonzero == 4


def test_allocate_hours_no_capacity_uses_full_avail(db_session):
    """daily_capacity=None — старое поведение (полная дневная норма)."""
    svc = ResourcePlanningService(db_session)
    start = date(2026, 5, 4)  # Monday
    days = [start + timedelta(days=i) for i in range(7) if (start + timedelta(days=i)).weekday() < 5]
    remaining = {"emp-1": {d: 8.0 for d in days}}

    segments = svc._allocate_hours(
        employee_id="emp-1",
        total_hours=16.0,
        earliest_start=start,
        deadline=start + timedelta(days=14),
        remaining=remaining,
        daily_capacity=None,
    )
    assert len(segments) == 1
    seg_start, seg_end, seg_hours, _ = segments[0]
    assert seg_hours == pytest.approx(16.0, abs=0.01)
    # 16 hours in 8h-days → 2 days
    nonzero = sum(1 for d in days if remaining["emp-1"][d] < 8.0)
    assert nonzero == 2
