"""Фабрики для тестов привлечения сотрудников из чужих команд."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Dict, Optional

from app.models import (
    BacklogItem,
    Employee,
    Issue,
    PlanningScenario,
    ResourcePlan,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.models.employee_team import EmployeeTeam


def make_employee(
    db,
    name: str,
    team: str,
    role: str = "developer",
    jira_account_id: Optional[str] = None,
    member: bool = True,
    is_active: bool = True,
) -> Employee:
    e = Employee(
        jira_account_id=jira_account_id or f"acc-{uuid.uuid4().hex[:12]}",
        display_name=name,
        role=role,
        team=team,
        is_active=is_active,
    )
    db.add(e)
    db.flush()
    if member:
        db.add(EmployeeTeam(employee_id=e.id, team=team, is_primary=True))
        db.flush()
    return e


def make_plan(
    db,
    team: str,
    scenario_status: str = "approved",
    plan_status: str = "ready",
    year: int = 2026,
    quarter: str = "Q1",
    scenario_updated_at: Optional[datetime] = None,
    **plan_kw,
) -> tuple[PlanningScenario, ResourcePlan]:
    sc = PlanningScenario(
        name=f"{team}-{scenario_status}-{uuid.uuid4().hex[:6]}",
        quarter=quarter,
        year=year,
        team=team,
        status=scenario_status,
    )
    if scenario_updated_at is not None:
        sc.updated_at = scenario_updated_at
    db.add(sc)
    db.flush()
    plan = ResourcePlan(
        team=team,
        quarter=quarter,
        year=year,
        status=plan_status,
        scenario_id=sc.id,
        **plan_kw,
    )
    db.add(plan)
    db.flush()
    return sc, plan


def add_item(
    db,
    scenario: PlanningScenario,
    title: str,
    dev: float = 0.0,
    analyst: float = 0.0,
    assignee: Optional[Employee] = None,
    issue: Optional[Issue] = None,
    priority: int = 1,
) -> BacklogItem:
    item = BacklogItem(
        title=title,
        priority=priority,
        estimate_analyst_hours=analyst,
        estimate_dev_hours=dev,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        assignee_employee_id=assignee.id if assignee else None,
        issue_id=issue.id if issue else None,
    )
    db.add(item)
    db.flush()
    db.add(
        ScenarioAllocation(
            scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
        )
    )
    db.flush()
    return item


def book(
    db,
    plan: ResourcePlan,
    item: BacklogItem,
    employee: Employee,
    daily: Dict[str, float],
    phase: str = "dev",
    **kw,
) -> ResourcePlanAssignment:
    """Бронь сотрудника в плане: фаза с посуточной раскладкой."""
    days = sorted(daily)
    a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase=phase,
        employee_id=employee.id,
        part_number=1,
        hours_allocated=sum(daily.values()),
        start_date=date.fromisoformat(days[0]),
        end_date=date.fromisoformat(days[-1]),
        daily_hours_json=json.dumps(daily),
        **kw,
    )
    db.add(a)
    db.flush()
    return a


def make_issue(
    db,
    project,
    key: str,
    developer: Optional[str] = None,
    parent: Optional[Issue] = None,
) -> Issue:
    i = Issue(
        jira_issue_id=f"j-{key}",
        key=key,
        summary=key,
        issue_type="Task",
        status="Open",
        project_id=project.id,
        developer_account_id=developer,
        parent_id=parent.id if parent else None,
    )
    db.add(i)
    db.flush()
    return i
