"""Если зафиксированная фаза стартует раньше конца предшественника —
получаем конфликт PREDECESSOR_VIOLATED.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models import (
    BacklogItem,
    Employee,
    PhasePredecessor,
    PlanConflict,
    PlanningScenario,
    ResourcePlan,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.models.employee_team import EmployeeTeam
from app.services.resource_planning_service import ResourcePlanningService


def _uid() -> str:
    return str(uuid.uuid4())


def _base_setup(db_session, team: str):
    """Создать: аналитик + разработчик, одна инициатива, план.
    Возвращает (plan, item, analyst_emp, dev_emp).
    """

    def _emp(role: str) -> Employee:
        e = Employee(
            jira_account_id=uuid.uuid4().hex[:16],
            display_name=f"{role}-{team}",
            team=team,
            is_active=True,
            role=role,
        )
        db_session.add(e)
        db_session.flush()
        db_session.add(EmployeeTeam(employee_id=e.id, team=team, is_primary=True))
        return e

    analyst = _emp("analyst")
    developer = _emp("developer")

    item = BacklogItem(
        title=f"pv-item-{team}",
        priority=1,
        estimate_analyst_hours=8.0,
        estimate_dev_hours=8.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        assignee_employee_id=analyst.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name=f"pv-scenario-{team}",
        quarter="Q2",
        year=2026,
        status="draft",
        team=team,
    )
    db_session.add(scenario)
    db_session.flush()

    db_session.add(
        ScenarioAllocation(
            scenario_id=scenario.id,
            backlog_item_id=item.id,
            included_flag=True,
        )
    )

    plan = ResourcePlan(
        team=team,
        quarter="Q2",
        year=2026,
        status="draft",
        scenario_id=scenario.id,
    )
    db_session.add(plan)
    db_session.commit()
    return plan, item, analyst, developer


def _make_assignments(db_session, plan, item, analyst_emp, dev_emp,
                      analyst_end: date, dev_start: date, dev_end: date,
                      with_predecessor: bool = True) -> tuple:
    """Создать два назначения (analyst, dev) с заданными датами и ребром."""
    analyst_a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="analyst",
        employee_id=analyst_emp.id,
        part_number=1,
        hours_allocated=8.0,
        start_date=date(2026, 4, 1),
        end_date=analyst_end,
        pinned_start=False,
        pinned_split=False,
    )
    db_session.add(analyst_a)
    db_session.flush()

    dev_a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        employee_id=dev_emp.id,
        part_number=1,
        hours_allocated=8.0,
        start_date=dev_start,
        end_date=dev_end,
        pinned_start=True,
        pinned_split=False,
    )
    db_session.add(dev_a)
    db_session.flush()

    if with_predecessor:
        db_session.add(
            PhasePredecessor(
                predecessor_assignment_id=analyst_a.id,
                successor_assignment_id=dev_a.id,
            )
        )

    db_session.commit()
    return analyst_a, dev_a


def _run_detector(db_session, plan, item, analyst_emp, dev_emp, assignments) -> list:
    """Запустить только детектор конфликтов и вернуть PREDECESSOR_VIOLATED."""
    from app.services.conflict_aggregator import aggregate_conflicts

    svc = ResourcePlanningService(db_session)
    svc._last_leveling_events = []

    employees = [analyst_emp, dev_emp]
    q_end = date(2026, 6, 30)

    dicts = svc._build_conflict_dicts(plan, assignments, employees, q_end)
    dicts = aggregate_conflicts(dicts, db_session=db_session)
    svc._persist_conflicts(plan.id, dicts)
    db_session.commit()

    return (
        db_session.execute(
            select(PlanConflict).where(
                PlanConflict.plan_id == plan.id,
                PlanConflict.type == "PREDECESSOR_VIOLATED",
            )
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# Test 1: Violated — pinned dev starts before analyst ends
# ---------------------------------------------------------------------------

def test_predecessor_violated_detected(db_session):
    """Аналитик заканчивает 2026-04-20, dev зафиксирован на 2026-04-13 —
    должен появиться ровно 1 конфликт PREDECESSOR_VIOLATED для dev."""
    plan, item, analyst_emp, dev_emp = _base_setup(db_session, "T_PV1")

    analyst_a, dev_a = _make_assignments(
        db_session, plan, item, analyst_emp, dev_emp,
        analyst_end=date(2026, 4, 20),
        dev_start=date(2026, 4, 13),   # BEFORE analyst ends
        dev_end=date(2026, 4, 18),
        with_predecessor=True,
    )

    conflicts = _run_detector(
        db_session, plan, item, analyst_emp, dev_emp,
        [analyst_a, dev_a],
    )

    assert len(conflicts) == 1, (
        f"Expected 1 PREDECESSOR_VIOLATED conflict, got {len(conflicts)}"
    )
    assert conflicts[0].severity == "warning"


# ---------------------------------------------------------------------------
# Test 2: Not violated — dev starts after analyst ends
# ---------------------------------------------------------------------------

def test_predecessor_not_violated(db_session):
    """Аналитик заканчивает 2026-04-13, dev стартует 2026-04-15 —
    конфликтов PREDECESSOR_VIOLATED быть не должно."""
    plan, item, analyst_emp, dev_emp = _base_setup(db_session, "T_PV2")

    analyst_a, dev_a = _make_assignments(
        db_session, plan, item, analyst_emp, dev_emp,
        analyst_end=date(2026, 4, 13),
        dev_start=date(2026, 4, 15),   # AFTER analyst ends — OK
        dev_end=date(2026, 4, 20),
        with_predecessor=True,
    )

    conflicts = _run_detector(
        db_session, plan, item, analyst_emp, dev_emp,
        [analyst_a, dev_a],
    )

    assert len(conflicts) == 0, (
        f"Expected 0 PREDECESSOR_VIOLATED conflicts, got {len(conflicts)}: "
        f"{[c.message for c in conflicts]}"
    )


# ---------------------------------------------------------------------------
# Test 3: No predecessor — no PREDECESSOR_VIOLATED even if phase starts early
# ---------------------------------------------------------------------------

def test_no_predecessor_no_conflict(db_session):
    """Фаза без предшественника не вызывает PREDECESSOR_VIOLATED,
    даже если стартует очень рано."""
    plan, item, analyst_emp, dev_emp = _base_setup(db_session, "T_PV3")

    analyst_a, dev_a = _make_assignments(
        db_session, plan, item, analyst_emp, dev_emp,
        analyst_end=date(2026, 4, 20),
        dev_start=date(2026, 1, 1),   # Very early — but no predecessor edge
        dev_end=date(2026, 1, 5),
        with_predecessor=False,        # No edge
    )

    conflicts = _run_detector(
        db_session, plan, item, analyst_emp, dev_emp,
        [analyst_a, dev_a],
    )

    assert len(conflicts) == 0, (
        f"Expected 0 PREDECESSOR_VIOLATED conflicts (no predecessor), got {len(conflicts)}"
    )
