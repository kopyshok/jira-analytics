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


def test_delay_within_slack_shifts_assignment_when_slack_available():
    """Если у назначения есть slack ≥ overload_days, оно сдвигается, не эскалируется."""
    leveler = RcpspLeveler()
    a1 = _mk_assignment(
        "A1", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 6.0, item_id="I1"
    )
    # a2 имеет slack=5 — может быть отодвинут на 1 день
    a2 = _mk_assignment(
        "A2", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 4.0, item_id="I2"
    )
    a2.slack_days = 5.0
    avail = {"EMP-1": {date(2026, 4, 1): 8.0, date(2026, 4, 2): 8.0}}
    events = leveler.level([a1, a2], avail, q_end=date(2026, 4, 30))

    # a2 должен сдвинуться на 1 день
    assert a2.start_date == date(2026, 4, 2)
    assert a2.end_date == date(2026, 4, 2)
    # должно быть событие delay
    delay_events = [e for e in events if e.action == "delay"]
    assert len(delay_events) == 1
    assert delay_events[0].assignment_id == "A2"
    assert delay_events[0].delta_days == 1


def test_reassign_to_peer_when_delay_not_possible():
    """Если slack=0 но есть peer с той же ролью и свободным окном → reassign."""
    leveler = RcpspLeveler()
    a1 = _mk_assignment(
        "A1", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 6.0, item_id="I1"
    )
    a2 = _mk_assignment(
        "A2", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 4.0, item_id="I2"
    )
    a2.slack_days = 0.0
    avail = {
        "EMP-1": {date(2026, 4, 1): 8.0},
        "EMP-2": {date(2026, 4, 1): 8.0},
    }
    peers = {"EMP-1": ["EMP-1", "EMP-2"]}  # role pool
    events = leveler.level([a1, a2], avail, q_end=date(2026, 4, 30), role_pools=peers)
    reassign_events = [e for e in events if e.action == "reassign"]
    assert len(reassign_events) == 1
    assert reassign_events[0].assignment_id == "A2"
    assert reassign_events[0].to_employee_id == "EMP-2"
    assert a2.employee_id == "EMP-2"


def test_escalate_when_no_slack_no_peer():
    """Slack=0 + нет peer → событие escalate с overload_pct."""
    leveler = RcpspLeveler()
    a1 = _mk_assignment(
        "A1", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 6.0, item_id="I1"
    )
    a2 = _mk_assignment(
        "A2", "EMP-1", date(2026, 4, 1), date(2026, 4, 1), 4.0, item_id="I2"
    )
    a2.slack_days = 0.0
    avail = {"EMP-1": {date(2026, 4, 1): 8.0}}
    events = leveler.level(
        [a1, a2], avail, q_end=date(2026, 4, 30), role_pools={"EMP-1": ["EMP-1"]}
    )
    esc = [e for e in events if e.action == "escalate"]
    assert len(esc) >= 1
    assert esc[0].overload_pct >= 100.0
