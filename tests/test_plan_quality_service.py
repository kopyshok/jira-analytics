"""Tests for PlanQualityService."""

import uuid
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.employee import Employee
from app.services.plan_quality_service import PlanQualityService


def _make_employee(db: Session, name: str = "Иванов И.И.") -> Employee:
    emp = Employee(
        jira_account_id=uuid.uuid4().hex[:8],
        display_name=name,
        team="Команда А",
        is_active=True,
    )
    db.add(emp)
    db.flush()
    return emp


def test_quality_empty_plan_returns_zeros(db_session: Session):
    plan = ResourcePlan(team="Команда А", quarter="Q2", year=2026, status="ready")
    db_session.add(plan)
    db_session.flush()

    metric = PlanQualityService(db_session).compute(plan.id)

    assert metric["plan_id"] == plan.id
    assert metric["overload_days_pct"] == 0.0
    assert metric["late_count"] == 0
    assert metric["mean_utilization_pct"] == 0.0


def test_quality_counts_overload_when_assignment_exceeds_capacity(db_session: Session):
    """Один сотрудник, 2 параллельных назначения по 8ч/день каждое = перегруз 200%."""
    emp = _make_employee(db_session)
    plan = ResourcePlan(team="Команда А", quarter="Q2", year=2026, status="ready")
    db_session.add(plan)
    db_session.flush()

    # Два пересекающихся назначения один и тот же день
    for _ in range(2):
        db_session.add(ResourcePlanAssignment(
            plan_id=plan.id,
            backlog_item_id="dummy",  # FK relaxed in test fixture
            phase="dev",
            employee_id=emp.id,
            hours_allocated=8.0,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 1),
        ))
    db_session.flush()

    metric = PlanQualityService(db_session).compute(plan.id)

    # День один, один сотрудник, перегружен → 100% перегруза
    assert metric["overload_days_pct"] > 0.0


def test_quality_counts_late_assignments(db_session: Session):
    """Назначение с end_date после конца квартала считается просрочкой."""
    emp = _make_employee(db_session)
    plan = ResourcePlan(team="Команда А", quarter="Q2", year=2026, status="ready")
    db_session.add(plan)
    db_session.flush()

    # Q2 2026 заканчивается 2026-06-30; end_date на следующий день → просрочка
    db_session.add(ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id="dummy",
        phase="dev",
        employee_id=emp.id,
        hours_allocated=8.0,
        start_date=date(2026, 6, 30),
        end_date=date(2026, 7, 1),
    ))
    db_session.flush()

    metric = PlanQualityService(db_session).compute(plan.id)

    assert metric["late_count"] == 1
