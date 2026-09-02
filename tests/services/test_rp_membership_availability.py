"""Доступность сотрудника режется датами участия в команде плана."""
import uuid
from datetime import date

from app.models import Employee
from app.models.employee_team import EmployeeTeam
from app.services.resource_planning_service import ResourcePlanningService


def _emp(db_session, joined, left=None, team="T-mem"):
    e = Employee(
        jira_account_id=f"acc-{uuid.uuid4().hex[:12]}",
        display_name="Пришедший",
        role="developer",
        team=team,
        is_active=True,
    )
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)
    db_session.add(
        EmployeeTeam(
            employee_id=e.id, team=team, is_primary=True,
            joined_at=joined, left_at=left,
        )
    )
    db_session.commit()
    return e


def test_days_before_join_are_zero(db_session):
    emp = _emp(db_session, joined=date(2026, 7, 20))
    svc = ResourcePlanningService(db_session)
    avail = svc.build_availability(
        [emp], date(2026, 7, 1), date(2026, 7, 31), [], team="T-mem"
    )[emp.id]
    assert avail[date(2026, 7, 15)] == 0.0   # среда до входа в команду
    assert avail[date(2026, 7, 21)] > 0.0    # вторник после входа


def test_days_after_leave_are_zero(db_session):
    emp = _emp(db_session, joined=None, left=date(2026, 7, 10))
    svc = ResourcePlanningService(db_session)
    avail = svc.build_availability(
        [emp], date(2026, 7, 1), date(2026, 7, 31), [], team="T-mem"
    )[emp.id]
    assert avail[date(2026, 7, 8)] > 0.0
    assert avail[date(2026, 7, 15)] == 0.0


def test_without_team_arg_membership_ignored(db_session):
    """Вызов без команды (прежние места) считает как раньше — голый календарь."""
    emp = _emp(db_session, joined=date(2026, 7, 20))
    svc = ResourcePlanningService(db_session)
    avail = svc.build_availability(
        [emp], date(2026, 7, 1), date(2026, 7, 31), []
    )[emp.id]
    assert avail[date(2026, 7, 15)] > 0.0


def test_scheduler_starts_after_join_date(db_session):
    """Пришедший в середине квартала не получает работу до даты входа."""
    import uuid as _uuid
    from app.models import (
        BacklogItem,
        PlanningScenario,
        ResourcePlan,
        ResourcePlanAssignment,
        ScenarioAllocation,
    )
    from sqlalchemy import select

    team = "T_JOIN"

    def _member(role, name, joined=None):
        e = Employee(
            jira_account_id=_uuid.uuid4().hex[:16],
            display_name=name,
            team=team,
            is_active=True,
            role=role,
        )
        db_session.add(e)
        db_session.flush()
        db_session.add(
            EmployeeTeam(
                employee_id=e.id, team=team, is_primary=True, joined_at=joined
            )
        )
        return e

    analyst = _member("analyst", "Аналитик")
    dev = _member("developer", "Новичок", joined=date(2026, 2, 16))

    item = BacklogItem(
        title="join-test",
        priority=1,
        estimate_analyst_hours=8.0,
        estimate_dev_hours=24.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        assignee_employee_id=analyst.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="join-scenario", quarter="Q1", year=2026, status="draft", team=team
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(
        ScenarioAllocation(
            scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
        )
    )
    plan = ResourcePlan(
        team=team, quarter="Q1", year=2026, status="draft", scenario_id=scenario.id
    )
    db_session.add(plan)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    dev_row = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "dev",
            )
        )
        .scalars()
        .first()
    )
    assert dev_row is not None and dev_row.employee_id == dev.id
    assert dev_row.start_date >= date(2026, 2, 16)
