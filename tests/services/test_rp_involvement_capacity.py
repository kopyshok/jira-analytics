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
    """20ч, daily_capacity=5.6 → 4 дня; промежуточные дни блокируются целиком,
    остаток последнего дня сохраняется для spillover (last-day leftover).

    Остаток последнего дня ограничен потолком вовлечённости: на 4-й день фаза
    взяла 3.2 ч из потолка 5.6 → доступно следующей фазе 5.6 − 3.2 = 2.4 ч
    (а не 8 − 3.2 = 4.8 — это превысило бы involvement-ёмкость дня).
    """
    svc = ResourcePlanningService(db_session)
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
    # Семантика: промежуточные дни заняты целиком (relay), но на последнем дне
    # остаётся leftover для фазы следующей по приоритету инициативы.
    blocked = sum(1 for d in days if remaining["emp-1"][d] == 0.0)
    assert blocked == 3  # первые 3 дня по 5.6ч заблокированы полностью
    leftover_idx = days.index(seg_end)
    assert remaining["emp-1"][days[leftover_idx]] == pytest.approx(5.6 - 3.2, abs=0.01)
    # Длительность бара: 4 дня от seg_start до seg_end.
    assert (seg_end - seg_start).days == 3


def test_last_day_leftover_capped_by_involvement(db_session):
    """Остаток последнего дня фазы ограничен ёмкостью по вовлечённости,
    а не полной нормой дня.

    Сотрудник: 8 ч/день. Фаза 5 ч при daily_capacity=5.6 (вовлечённость 70%)
    укладывается в один день. Доступным для следующей по приоритету фазы
    должно остаться 5.6 − 5 = 0.6 ч (а не 8 − 5 = 3 ч). Иначе две фазы
    разных задач за день дают 5 + 3 = 8 ч — перегруз сверх 5.6.
    """
    svc = ResourcePlanningService(db_session)
    day = date(2026, 5, 4)  # Monday
    remaining = {"emp-1": {day: 8.0}}

    svc._allocate_hours(
        employee_id="emp-1",
        total_hours=5.0,
        earliest_start=day,
        deadline=day + timedelta(days=20),
        remaining=remaining,
        daily_capacity=5.6,
    )
    assert remaining["emp-1"][day] == pytest.approx(0.6, abs=0.01)


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
