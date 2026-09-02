"""Планировщик берёт вовлечённость из справочника, когда у задачи она не задана."""

import uuid

from sqlalchemy import select

from app.models import (
    BacklogItem,
    Employee,
    InvolvementDefault,
    PlanningScenario,
    ResourcePlan,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.models.employee_team import EmployeeTeam
from app.services.resource_planning_service import ResourcePlanningService


def _plan_with_dev_task(db_session, team: str, involvement_dev=None) -> ResourcePlan:
    analyst = Employee(
        jira_account_id=uuid.uuid4().hex[:16], display_name=f"an-{team}",
        team=team, is_active=True, role="analyst",
    )
    dev = Employee(
        jira_account_id=uuid.uuid4().hex[:16], display_name=f"dev-{team}",
        team=team, is_active=True, role="developer",
    )
    db_session.add_all([analyst, dev])
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(employee_id=analyst.id, team=team, is_primary=True),
        EmployeeTeam(employee_id=dev.id, team=team, is_primary=True),
    ])
    item = BacklogItem(
        title="inv-default-test", priority=1,
        estimate_dev_hours=32.0, involvement_dev=involvement_dev,
        assignee_employee_id=analyst.id,
    )
    db_session.add(item)
    db_session.flush()
    scenario = PlanningScenario(
        name=f"inv-{team}", quarter="Q1", year=2026, status="draft", team=team,
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True,
    ))
    plan = ResourcePlan(
        team=team, quarter="Q1", year=2026, status="draft", scenario_id=scenario.id,
    )
    db_session.add(plan)
    db_session.commit()
    return plan


def _dev_phase_days(db_session, plan_id: str) -> int:
    a = db_session.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_id,
            ResourcePlanAssignment.phase == "dev",
        )
    ).scalars().first()
    assert a is not None and a.start_date and a.end_date
    return (a.end_date - a.start_date).days + 1


def test_team_default_involvement_stretches_phase(db_session):
    """Половинная вовлечённость из справочника растягивает фазу вдвое."""
    plain = _plan_with_dev_task(db_session, "T_INV_PLAIN")
    ResourcePlanningService(db_session).compute_schedule(plain.id)
    full_days = _dev_phase_days(db_session, plain.id)

    db_session.add(InvolvementDefault(
        team="T_INV_DEFAULT", role="dev",
        effective_year=2026, effective_quarter=1, involvement=0.5,
    ))
    with_default = _plan_with_dev_task(db_session, "T_INV_DEFAULT")
    ResourcePlanningService(db_session).compute_schedule(with_default.id)

    assert _dev_phase_days(db_session, with_default.id) > full_days


def test_task_own_involvement_wins_over_team_default(db_session):
    """Значение, заданное у задачи, важнее справочника команды."""
    db_session.add(InvolvementDefault(
        team="T_INV_OWN", role="dev",
        effective_year=2026, effective_quarter=1, involvement=0.25,
    ))
    plain = _plan_with_dev_task(db_session, "T_INV_PLAIN2")
    own = _plan_with_dev_task(db_session, "T_INV_OWN", involvement_dev=1.0)
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plain.id)
    svc.compute_schedule(own.id)

    assert _dev_phase_days(db_session, own.id) == _dev_phase_days(db_session, plain.id)
