"""Раздробленная фаза сохраняет место в очереди приоритета.

Воспроизводит OS-91446: анализ задачи с высшим приоритетом раздроблен на
две части. Баг: при пересчёте части раздробленной фазы раскладывались
отдельным проходом ПОСЛЕ всех остальных задач — на остатки ёмкости. Задача
уезжала за задачи с меньшим приоритетом (в декабрь), а при следующих
пересчётах уже не могла вернуться раньше своей прежней даты.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.models import (
    BacklogItem,
    Employee,
    PlanningScenario,
    ResourcePlan,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.models.employee_team import EmployeeTeam
from app.services.resource_planning_service import ResourcePlanningService


def _emp(db_session, team: str, role: str) -> Employee:
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


def _next_working_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def _rows(db_session, plan_id: str, item_id: str, phase: str):
    return (
        db_session.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.backlog_item_id == item_id,
                ResourcePlanAssignment.phase == phase,
            )
            .order_by(ResourcePlanAssignment.part_number)
        )
        .scalars()
        .all()
    )


def test_split_phase_keeps_priority_order(db_session):
    team = "T_SPLIT_PRIORITY"
    _emp(db_session, team, "analyst")
    _emp(db_session, team, "developer")

    top = BacklogItem(
        title="top", priority=9,
        estimate_analyst_hours=40.0, estimate_dev_hours=40.0,
    )
    low = BacklogItem(
        title="low", priority=3,
        estimate_analyst_hours=80.0, estimate_dev_hours=40.0,
    )
    db_session.add_all([top, low])
    db_session.flush()

    scenario = PlanningScenario(
        name="split-priority", quarter="Q4", year=2026, status="draft", team=team,
    )
    db_session.add(scenario)
    db_session.flush()
    for it in (top, low):
        db_session.add(
            ScenarioAllocation(
                scenario_id=scenario.id, backlog_item_id=it.id, included_flag=True,
            )
        )
    plan = ResourcePlan(
        team=team, quarter="Q4", year=2026, status="draft",
        scenario_id=scenario.id,
    )
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    top_an = _rows(db_session, plan.id, top.id, "analyst")
    low_an = _rows(db_session, plan.id, low.id, "analyst")
    assert top_an[0].start_date < low_an[0].start_date
    q_start = top_an[0].start_date

    svc.split_assignment(top_an[0].id, [20.0, 20.0], cascade=True)
    db_session.commit()

    # Два пересчёта подряд: второй ловит «храповик» — раньше часть не могла
    # встать раньше даты, полученной прошлым пересчётом.
    for _ in range(2):
        svc.compute_schedule(plan.id)
        db_session.expire_all()

        parts = _rows(db_session, plan.id, top.id, "analyst")
        low_an = _rows(db_session, plan.id, low.id, "analyst")
        assert len(parts) == 2
        assert parts[0].start_date == q_start, (
            f"Первая часть анализа старшей задачи должна начаться {q_start}, "
            f"а стоит {parts[0].start_date} — ушла за младшую задачу"
        )
        # Вторая часть — сразу за первой, а не за младшей задачей. Остаток
        # последнего дня первой части младшая задача забрать может.
        expected = _next_working_day(parts[0].end_date)
        assert parts[1].start_date == expected, (
            f"Вторая часть должна начаться {expected}, а стоит "
            f"{parts[1].start_date}"
        )
        assert parts[1].end_date < low_an[0].end_date
