"""Тесты сохранения ручных правок (pinned_start / pinned_split) при recompute."""

import uuid
from datetime import date, datetime

import pytest
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


@pytest.fixture
def sample_plan(db_session):
    """Команда из 2 сотрудников + инициатива со всеми 4 фазами."""
    team = "T_PIN"

    def _emp(role: str) -> Employee:
        e = Employee(
            jira_account_id=uuid.uuid4().hex[:16],
            display_name=f"{role.capitalize()}-pin",
            team=team,
            is_active=True,
            role=role,
        )
        db_session.add(e)
        db_session.flush()
        et = EmployeeTeam(employee_id=e.id, team=team, is_primary=True)
        db_session.add(et)
        return e

    analyst = _emp("analyst")
    _emp("developer")

    item = BacklogItem(
        title="pin-test",
        priority=1,
        estimate_analyst_hours=16.0,
        estimate_dev_hours=24.0,
        estimate_qa_hours=8.0,
        estimate_opo_hours=8.0,
        opo_analyst_ratio=0.5,
        assignee_employee_id=analyst.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="pin-scenario",
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
    return plan


def test_pinned_start_preserved_on_recompute(db_session, sample_plan):
    """Закреплённая user-ом дата start_date не меняется при пересчёте."""
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(sample_plan.id)

    a = (
        db_session.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == sample_plan.id,
                ResourcePlanAssignment.phase == "analyst",
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    assert a is not None

    fixed_start = date(2026, 4, 15)
    a.start_date = fixed_start
    a.pinned_start = True
    a.manual_edit_at = datetime.utcnow()
    db_session.commit()

    svc.compute_schedule(sample_plan.id)
    db_session.refresh(a)
    assert a.start_date == fixed_start


def test_pinned_split_not_merged(db_session, sample_plan):
    """Пользовательский split фазы сохраняется после пересчёта."""
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(sample_plan.id)

    rows = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == sample_plan.id,
                ResourcePlanAssignment.phase == "analyst",
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    original = rows[0]

    # Разбить аналитическую фазу на 2 части по дням.
    half_hours = (original.hours_allocated or 16.0) / 2.0
    middle = original.start_date or date(2026, 4, 1)
    part2_start = date(middle.year, middle.month, middle.day + 7)
    original.hours_allocated = half_hours
    original.end_date = date(middle.year, middle.month, middle.day + 6)
    original.pinned_split = True
    original.manual_edit_at = datetime.utcnow()

    part2 = ResourcePlanAssignment(
        plan_id=sample_plan.id,
        backlog_item_id=original.backlog_item_id,
        phase="analyst",
        employee_id=original.employee_id,
        part_number=2,
        hours_allocated=half_hours,
        start_date=part2_start,
        end_date=date(part2_start.year, part2_start.month, part2_start.day + 6),
        pinned_split=True,
        manual_edit_at=datetime.utcnow(),
    )
    db_session.add(part2)
    db_session.commit()

    svc.compute_schedule(sample_plan.id)

    rows = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == sample_plan.id,
                ResourcePlanAssignment.phase == "analyst",
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    assert {r.part_number for r in rows} == {1, 2}
    assert all(r.pinned_split for r in rows)
