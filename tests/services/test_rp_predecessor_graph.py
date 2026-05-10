"""Тесты графа предшественников фаз в compute_schedule."""

import uuid

import pytest
from sqlalchemy import select

from app.models import (
    BacklogItem,
    Employee,
    PhasePredecessor,
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
    team = "T_PRED"

    def _emp(role: str) -> Employee:
        e = Employee(
            jira_account_id=uuid.uuid4().hex[:16],
            display_name=f"{role.capitalize()}-pred",
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
        title="pred-test",
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
        name="pred-scenario",
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


def test_default_chain_creates_analyst_dev_qa_opo(db_session, sample_plan):
    """Первый compute создаёт дефолтную цепочку рёбер analyst→dev→qa→opo."""
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(sample_plan.id)
    rows = (
        db_session.execute(
            select(PhasePredecessor)
            .join(
                ResourcePlanAssignment,
                PhasePredecessor.successor_assignment_id == ResourcePlanAssignment.id,
            )
            .where(ResourcePlanAssignment.plan_id == sample_plan.id)
        )
        .scalars()
        .all()
    )
    assert len(rows) >= 3


def test_custom_predecessor_overrides_chain(db_session, sample_plan):
    """qa→analyst (вместо qa→dev): qa стартует не позже окончания dev."""
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(sample_plan.id)

    rows = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == sample_plan.id
            )
        )
        .scalars()
        .all()
    )
    qa = next(a for a in rows if a.phase == "qa")
    dev = next(a for a in rows if a.phase == "dev")
    analyst = next(a for a in rows if a.phase == "analyst")

    # Удалить существующие предшественники qa и привязать qa только к analyst.
    db_session.execute(
        PhasePredecessor.__table__.delete().where(
            PhasePredecessor.successor_assignment_id == qa.id
        )
    )
    db_session.add(
        PhasePredecessor(
            successor_assignment_id=qa.id,
            predecessor_assignment_id=analyst.id,
        )
    )
    db_session.commit()

    svc.compute_schedule(sample_plan.id)

    rows = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == sample_plan.id
            )
        )
        .scalars()
        .all()
    )
    qa2 = next(a for a in rows if a.phase == "qa")
    dev2 = next(a for a in rows if a.phase == "dev")

    assert qa2.start_date is not None
    assert dev2.end_date is not None
    # qa параллельна dev: стартует не позже окончания dev.
    assert qa2.start_date <= dev2.end_date


def test_cycle_rejected(db_session, sample_plan):
    """Добавление ребра, замыкающего цикл, бросает ValueError."""
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(sample_plan.id)

    rows = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == sample_plan.id
            )
        )
        .scalars()
        .all()
    )
    analyst = next(a for a in rows if a.phase == "analyst")
    dev = next(a for a in rows if a.phase == "dev")

    # Дефолтная цепочка содержит analyst→dev (succ=dev, pred=analyst).
    # Добавление succ=analyst, pred=dev создаст цикл analyst→dev→analyst.
    with pytest.raises(ValueError, match="cycle"):
        svc.add_predecessor(successor_id=analyst.id, predecessor_id=dev.id)
