"""Unit tests for PyJobShopSolverService на синтетических данных."""

import uuid
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.backlog_item import BacklogItem
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.services.pyjobshop_solver_service import PyJobShopSolverService


def _make_employee(db: Session, role: str, team: str = "A") -> Employee:
    emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name=f"{role.capitalize()}1",
        team=team,
        is_active=True,
        role=role,
    )
    db.add(emp)
    db.flush()
    return emp


@pytest.fixture
def simple_plan(db_session: Session):
    """1 сотрудник-разработчик, 1 backlog с phase=dev на 16ч → 2 рабочих дня."""
    emp = _make_employee(db_session, role="developer", team="A")

    item = BacklogItem(
        title="Story 1",
        priority=1,
        estimate_dev_hours=16.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="A", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        hours_allocated=16.0,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
    )
    db_session.add(assignment)
    db_session.commit()
    return {"plan": plan, "employee": emp, "item": item, "assignment": assignment}


def test_solver_assigns_dev_to_developer(simple_plan, db_session: Session):
    plan = simple_plan["plan"]
    emp = simple_plan["employee"]

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    # Один dev на эту задачу — должен быть назначен наш единственный разработчик
    assert a["assignee_employee_id"] == emp.id
