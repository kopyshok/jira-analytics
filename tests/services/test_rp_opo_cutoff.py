"""С квартала отсечки фаза ОПЭ не планируется, её часы уходят в Анализ и Разработку."""

import uuid

from sqlalchemy import select

from app.models import (
    AppSetting,
    BacklogItem,
    Employee,
    PlanningScenario,
    ResourcePlan,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.models.employee_team import EmployeeTeam
from app.services import opo_policy
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


def _plan(db_session, team: str, year: int, quarter: str) -> ResourcePlan:
    analyst = _emp(db_session, team, "analyst")
    _emp(db_session, team, "developer")
    item = BacklogItem(
        title="opo-cutoff-test",
        priority=1,
        estimate_analyst_hours=16.0,
        estimate_dev_hours=16.0,
        estimate_qa_hours=8.0,
        estimate_opo_hours=10.0,
        opo_analyst_ratio=0.4,
        assignee_employee_id=analyst.id,
    )
    db_session.add(item)
    db_session.flush()
    scenario = PlanningScenario(
        name=f"opo-cutoff-{team}", quarter=quarter, year=year, status="draft", team=team,
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True,
    ))
    plan = ResourcePlan(
        team=team, quarter=quarter, year=year, status="draft", scenario_id=scenario.id,
    )
    db_session.add(plan)
    db_session.commit()
    return plan


def _hours_by_phase(db_session, plan_id: str) -> dict[str, float]:
    rows = db_session.execute(
        select(ResourcePlanAssignment).where(ResourcePlanAssignment.plan_id == plan_id)
    ).scalars().all()
    out: dict[str, float] = {}
    for a in rows:
        out[a.phase] = out.get(a.phase, 0.0) + float(a.hours_allocated or 0.0)
    return out


def test_opo_phase_planned_before_cutoff(db_session):
    db_session.add(AppSetting(key=opo_policy.SETTING_KEY, value="2026Q4"))
    plan = _plan(db_session, "T_OPO_ON", 2026, "Q3")

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    hours = _hours_by_phase(db_session, plan.id)
    assert round(hours.get("opo", 0.0), 2) == 10.0
    assert round(hours["analyst"], 2) == 16.0
    assert round(hours["dev"], 2) == 16.0


def test_opo_hours_folded_into_analyst_and_dev_from_cutoff(db_session):
    db_session.add(AppSetting(key=opo_policy.SETTING_KEY, value="2026Q4"))
    plan = _plan(db_session, "T_OPO_OFF", 2026, "Q4")

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    hours = _hours_by_phase(db_session, plan.id)
    assert "opo" not in hours
    assert round(hours["analyst"], 2) == 20.0  # 16 + 10 * 0.4
    assert round(hours["dev"], 2) == 22.0      # 16 + 10 * 0.6
    assert round(hours["qa"], 2) == 8.0
