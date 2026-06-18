"""Вторая часть разбитой фазы не должна «спотыкаться о собственную тень».

Воспроизводит ITL-361: разработка разбита на 2 части, первая часть отвязана
от анализа (идёт параллельно с начала квартала), вторая часть сохраняет
предшественника «Анализ». Разработчик в остальном свободен.

Баг: вторая часть раскладывалась дважды — сначала шагом сдвига по
предшественникам (списывал дни), затем проходом переразбивки pinned_split,
который НЕ возвращал ранее списанные строкой дни. Из-за этого раскладчик
видел дни сразу после анализа занятыми этой же строкой и сдвигал вторую
часть вперёд на свободные дни.
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


def test_split_part2_starts_right_after_predecessor(db_session):
    team = "T_SPLIT_SHADOW"
    _emp(db_session, team, "analyst")
    _emp(db_session, team, "developer")

    item = BacklogItem(
        title="split-shadow-test",
        priority=1,
        estimate_analyst_hours=80.0,
        estimate_dev_hours=120.0,
        estimate_qa_hours=8.0,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="split-shadow-scenario",
        quarter="Q3",
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
        quarter="Q3",
        year=2026,
        status="draft",
        scenario_id=scenario.id,
    )
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    # Разбить разработку на 2 равные части.
    dev_row = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "dev",
                ResourcePlanAssignment.part_number == 1,
            )
        )
        .scalars()
        .one()
    )
    svc.split_assignment(dev_row.id, [60.0, 60.0], cascade=False)
    db_session.commit()

    analyst_row = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "analyst",
            )
        )
        .scalars()
        .one()
    )
    dev_p1 = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "dev",
                ResourcePlanAssignment.part_number == 1,
            )
        )
        .scalars()
        .one()
    )
    dev_p2_pre = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "dev",
                ResourcePlanAssignment.part_number == 2,
            )
        )
        .scalars()
        .one()
    )
    # Первую часть отвязать (параллельный старт), вторую — оставить за анализом.
    svc.set_predecessors(dev_p1.id, [])
    svc.set_predecessors(dev_p2_pre.id, [analyst_row.id])
    dev_p1.predecessors_user_set = True
    dev_p2_pre.predecessors_user_set = True
    db_session.commit()

    # Пересчёт.
    svc.compute_schedule(plan.id)
    db_session.expire_all()

    analyst = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "analyst",
            )
        )
        .scalars()
        .one()
    )
    dev_p2 = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "dev",
                ResourcePlanAssignment.part_number == 2,
            )
        )
        .scalars()
        .one()
    )

    assert analyst.end_date is not None and dev_p2.start_date is not None
    expected = _next_working_day(analyst.end_date)
    assert dev_p2.start_date == expected, (
        f"Вторая часть разработки должна стартовать {expected} "
        f"(сразу за анализом {analyst.end_date}), а стоит {dev_p2.start_date} — "
        f"раскладка сдвинула фазу на свободные дни из-за невозвращённого "
        f"собственного списания"
    )
