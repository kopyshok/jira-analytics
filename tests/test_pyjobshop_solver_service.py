"""Unit tests for PyJobShopSolverService на синтетических данных."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.absence import Absence
from app.models.absence_reason import AbsenceReason
from app.models.employee import Employee
from app.models.backlog_item import BacklogItem
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.scheduled_block import ScheduledBlock
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


def test_solver_respects_employee_absence(db_session: Session):
    """Задача не может стартовать в период отсутствия сотрудника."""
    # Q2 2026 starts 2026-04-01; employee is absent 2026-04-01 – 2026-04-15
    emp = Employee(
        jira_account_id=uuid.uuid4().hex[:8],
        display_name="DevAbsent",
        team="B",
        is_active=True,
        role="developer",
    )
    db_session.add(emp)
    db_session.flush()

    # Получаем или создаём причину отсутствия
    reason = db_session.scalars(
        select(AbsenceReason).where(AbsenceReason.code == "vacation")
    ).first()
    if reason is None:
        reason = AbsenceReason(code="vacation", label="Отпуск")
        db_session.add(reason)
        db_session.flush()

    absence = Absence(
        employee_id=emp.id,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 15),
        reason_id=reason.id,
    )
    db_session.add(absence)
    db_session.flush()

    item = BacklogItem(
        title="Task After Absence",
        priority=1,
        estimate_dev_hours=8.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="B", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        hours_allocated=8.0,
        start_date=date(2026, 4, 16),
        end_date=date(2026, 4, 16),
    )
    db_session.add(assignment)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    assert a["assignee_employee_id"] == emp.id
    # Задача должна стартовать ПОСЛЕ окончания отпуска (2026-04-15)
    assert a["start_date"] >= date(2026, 4, 16)


def test_solver_respects_employee_blocked_zone(db_session: Session):
    """Задача не стартует в заблокированный период (employee-scope ScheduledBlock)."""
    # Q2 2026 starts 2026-04-01; blocked 2026-04-01 – 2026-04-10 (закрытие месяца).
    # Первый доступный рабочий день после блока: 2026-04-13 (пн, т.к. 11-12 — выходные).
    emp = Employee(
        jira_account_id=uuid.uuid4().hex[:8],
        display_name="DevBlocked",
        team="C",
        is_active=True,
        role="developer",
    )
    db_session.add(emp)
    db_session.flush()

    block = ScheduledBlock(
        employee_id=emp.id,
        team=None,
        role_id=None,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 10),
        reason="Закрытие месяца",
    )
    db_session.add(block)
    db_session.flush()

    item = BacklogItem(
        title="Task After Block",
        priority=1,
        estimate_dev_hours=8.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="C", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        hours_allocated=8.0,
        start_date=date(2026, 4, 13),
        end_date=date(2026, 4, 13),
    )
    db_session.add(assignment)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    assert a["assignee_employee_id"] == emp.id
    # Задача должна стартовать не раньше 2026-04-13 (первый рабочий день после блока)
    assert a["start_date"] >= date(2026, 4, 13)


def test_solver_respects_team_wide_block(db_session: Session):
    """Team-wide ScheduledBlock (employee_id=None, role_id=None) блокирует сотрудника."""
    # Блок на всю команду D: 2026-04-01 – 2026-04-10.
    emp = Employee(
        jira_account_id=uuid.uuid4().hex[:8],
        display_name="DevTeamBlock",
        team="D",
        is_active=True,
        role="developer",
    )
    db_session.add(emp)
    db_session.flush()

    block = ScheduledBlock(
        employee_id=None,
        role_id=None,
        team="D",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 10),
        reason="Командный мораторий",
    )
    db_session.add(block)
    db_session.flush()

    item = BacklogItem(
        title="Task After Team Block",
        priority=1,
        estimate_dev_hours=8.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="D", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        hours_allocated=8.0,
        start_date=date(2026, 4, 13),
        end_date=date(2026, 4, 13),
    )
    db_session.add(assignment)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    assert a["assignee_employee_id"] == emp.id
    # Задача должна стартовать не раньше 2026-04-13 (первый рабочий день после блока)
    assert a["start_date"] >= date(2026, 4, 13)
