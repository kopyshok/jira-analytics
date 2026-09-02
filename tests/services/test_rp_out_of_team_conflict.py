"""Назначение на сотрудника после его выбытия из команды — конфликт OUT_OF_TEAM."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import (
    BacklogItem,
    Employee,
    PlanConflict,
    PlanningScenario,
    ResourcePlan,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.models.employee_team import EmployeeTeam
from app.services.resource_planning_service import ResourcePlanningService


@pytest.fixture
def sample_plan(db_session):
    """Команда из 2 сотрудников + инициатива на 2026 Q1."""
    team = "T_OOT"

    def _emp(role: str) -> Employee:
        e = Employee(
            jira_account_id=uuid.uuid4().hex[:16],
            display_name=f"{role.capitalize()}-oot",
            team=team,
            is_active=True,
            role=role,
        )
        db_session.add(e)
        db_session.flush()
        db_session.add(EmployeeTeam(employee_id=e.id, team=team, is_primary=True))
        return e

    analyst = _emp("analyst")
    _emp("developer")

    item = BacklogItem(
        title="oot-test",
        priority=1,
        estimate_analyst_hours=40.0,
        estimate_dev_hours=24.0,
        estimate_qa_hours=8.0,
        estimate_opo_hours=8.0,
        opo_analyst_ratio=0.5,
        assignee_employee_id=analyst.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="oot-scenario",
        quarter="Q1",
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
        quarter="Q1",
        year=2026,
        status="draft",
        scenario_id=scenario.id,
    )
    db_session.add(plan)
    db_session.commit()
    return plan, analyst


def test_assignment_after_departure_creates_conflict(db_session, sample_plan):
    """Задача стоит на сотруднике, который выбыл раньше её конца."""
    plan, analyst = sample_plan
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    a = (
        db_session.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "analyst",
                ResourcePlanAssignment.employee_id == analyst.id,
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    assert a is not None
    assert a.start_date and a.end_date and a.end_date > a.start_date

    # Строка закреплена по датам: пересчёт её не двигает, поэтому она и
    # остаётся висеть на выбывшем — именно этот случай ловит конфликт.
    # (Незакреплённые строки планировщик теперь сам не заводит за дату ухода.)
    a.pinned_start = True
    db_session.commit()

    # Сотрудник выбывает на второй день своей же фазы.
    membership = (
        db_session.execute(
            select(EmployeeTeam).where(
                EmployeeTeam.employee_id == analyst.id,
                EmployeeTeam.team == plan.team,
            )
        )
        .scalars()
        .one()
    )
    membership.left_at = a.start_date + timedelta(days=1)
    db_session.commit()

    svc.compute_schedule(plan.id)

    conflicts = (
        db_session.execute(
            select(PlanConflict).where(
                PlanConflict.plan_id == plan.id,
                PlanConflict.type == "OUT_OF_TEAM",
            )
        )
        .scalars()
        .all()
    )
    assert conflicts, "ожидался конфликт OUT_OF_TEAM"
    assert any(c.employee_id == analyst.id for c in conflicts)
    assert all(c.severity == "critical" for c in conflicts)


def test_no_conflict_while_employee_stays(db_session, sample_plan):
    """Без выбытия конфликта OUT_OF_TEAM нет."""
    plan, _analyst = sample_plan
    ResourcePlanningService(db_session).compute_schedule(plan.id)

    conflicts = (
        db_session.execute(
            select(PlanConflict).where(
                PlanConflict.plan_id == plan.id,
                PlanConflict.type == "OUT_OF_TEAM",
            )
        )
        .scalars()
        .all()
    )
    assert conflicts == []
