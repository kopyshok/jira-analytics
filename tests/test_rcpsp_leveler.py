"""Тесты для RcpspLeveler — пост-CPM выравнивание перегрузок."""

from datetime import date

from app.models import ResourcePlanAssignment
from app.services.rcpsp_leveler import RcpspLeveler


def test_leveler_empty_assignments_returns_no_events():
    leveler = RcpspLeveler()
    events = leveler.level(assignments=[], availability={}, q_end=date(2026, 6, 30))
    assert events == []


def _mk_assignment(id_, emp_id, start, end, hours, phase="dev", item_id="ITEM-1"):
    a = ResourcePlanAssignment(
        id=id_,
        plan_id="PLAN-1",
        backlog_item_id=item_id,
        phase=phase,
        employee_id=emp_id,
        part_number=1,
        hours_allocated=hours,
        start_date=start,
        end_date=end,
        is_on_critical_path=False,
        slack_days=10.0,
    )
    return a


def test_leveler_detects_overload_when_two_assignments_share_employee_day():
    """Два назначения на одного сотрудника на тот же день → overload событие."""
    leveler = RcpspLeveler()
    a1 = _mk_assignment(
        "A1", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 6.0, item_id="I1"
    )
    a2 = _mk_assignment(
        "A2", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 4.0, item_id="I2"
    )
    avail = {"EMP-1": {date(2026, 4, 1): 8.0}}
    overloads = leveler._detect_overload([a1, a2], avail)
    assert (date(2026, 4, 1), "EMP-1") in overloads
    assert overloads[(date(2026, 4, 1), "EMP-1")] == 10.0  # сумма demand
