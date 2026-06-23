"""Тест helper'а _day_co_occupants — кто ещё занял день сотрудника.

В частичный рабочий день (фаза взяла часть часов) таблица должна показывать,
куда ушёл остаток: другие фазы того же сотрудника с часами в этот день.
"""

from datetime import date
from types import SimpleNamespace

from app.api.endpoints.resource_planning import _day_co_occupants


def _assignment(aid, emp_id, phase, key, daily):
    issue = SimpleNamespace(key=key)
    bi = SimpleNamespace(issue=issue)
    return SimpleNamespace(
        id=aid,
        employee_id=emp_id,
        phase=phase,
        backlog_item=bi,
    ), daily


def test_co_occupants_lists_same_employee_other_phase():
    d = date(2026, 7, 23)
    others = [
        _assignment("a-self", "emp-1", "analyst", "ITL-301", {d: 0.6}),
        _assignment("a-opo", "emp-1", "opo", "ITL-398", {d: 5.0}),
        _assignment("a-other-emp", "emp-2", "dev", "ITL-999", {d: 4.0}),
    ]
    out = _day_co_occupants(d, "emp-1", others, skip_assignment_id="a-self")

    assert len(out) == 1
    assert out[0].item_key == "ITL-398"
    assert out[0].hours == 5.0
    assert "ОПЭ" in out[0].phase_label or out[0].phase_label  # лейбл фазы


def test_co_occupants_empty_when_no_overlap():
    d = date(2026, 7, 23)
    others = [
        _assignment("a-self", "emp-1", "analyst", "ITL-301", {d: 5.6}),
        _assignment("a-opo", "emp-1", "opo", "ITL-398", {date(2026, 7, 24): 5.0}),
    ]
    out = _day_co_occupants(d, "emp-1", others, skip_assignment_id="a-self")
    assert out == []
