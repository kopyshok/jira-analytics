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


def test_overload_uses_daily_hours_json_when_present():
    """
    Когда у assignment есть daily_hours_json — leveler читает per-day из него,
    а не делит hours_allocated равномерно по длине бара.

    Сценарий: 2 фазы пересекаются по date-range, но daily_hours показывает,
    что в один и тот же день они НЕ работают вместе → overload отсутствует.
    """
    leveler = RcpspLeveler()
    # Бар a1: 04.05-06.05, но реально работа только в 04.05 (8 ч).
    a1 = _mk_assignment(
        "A1", "EMP-1", date(2026, 5, 4), date(2026, 5, 6), 8.0, item_id="I1"
    )
    a1.daily_hours_json = '{"2026-05-04": 8.0}'
    # Бар a2: 05.05-07.05, реально работа только в 05.05 и 06.05.
    a2 = _mk_assignment(
        "A2", "EMP-1", date(2026, 5, 5), date(2026, 5, 7), 16.0, item_id="I2"
    )
    a2.daily_hours_json = '{"2026-05-05": 8.0, "2026-05-06": 8.0}'
    avail = {"EMP-1": {
        date(2026, 5, 4): 8.0,
        date(2026, 5, 5): 8.0,
        date(2026, 5, 6): 8.0,
        date(2026, 5, 7): 8.0,
    }}
    overloads = leveler._detect_overload([a1, a2], avail)
    # Никакого overload — на каждый день вес 8 ч из ровно одной фазы.
    assert overloads == {}


def test_overload_falls_back_to_even_distribution_without_daily_hours():
    """Старые assignment без daily_hours_json — fallback равномерное по рабочим дням."""
    leveler = RcpspLeveler()
    a1 = _mk_assignment(
        "A1", "EMP-1", date(2026, 5, 4), date(2026, 5, 5), 16.0, item_id="I1"
    )  # без daily_hours_json — fallback на 8 ч/день
    a2 = _mk_assignment(
        "A2", "EMP-1", date(2026, 5, 5), date(2026, 5, 5), 4.0, item_id="I2"
    )
    avail = {"EMP-1": {date(2026, 5, 4): 8.0, date(2026, 5, 5): 8.0}}
    overloads = leveler._detect_overload([a1, a2], avail)
    # 05.05: a1=8 + a2=4 = 12 > 8 → overload
    assert (date(2026, 5, 5), "EMP-1") in overloads
    assert overloads[(date(2026, 5, 5), "EMP-1")] == 12.0


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
    assert len(esc) == 1
    assert esc[0].overload_pct >= 100.0
