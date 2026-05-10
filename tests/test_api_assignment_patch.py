"""Tests for PATCH /resource-planning/resource-plans/{plan_id}/assignments/{id}.

Покрывает: pinned_start/pinned_employee/predecessor_ids + проверка цикла.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def ready_plan(db_session):
    """План с inception-сценарием: 1 инициатива, 4 фазы, 2 сотрудника."""
    from app.models import (
        BacklogItem,
        Employee,
        PlanningScenario,
        ResourcePlan,
        ScenarioAllocation,
    )
    from app.models.employee_team import EmployeeTeam
    from app.services.resource_planning_service import ResourcePlanningService

    team = "T_PATCH"

    def _emp(role: str) -> Employee:
        e = Employee(
            jira_account_id=uuid.uuid4().hex[:16],
            display_name=f"{role.capitalize()}",
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
    dev2 = _emp("developer")

    item = BacklogItem(
        title="patch-test",
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
        name="patch-scenario",
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

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    return {"plan_id": plan.id, "alt_employee_id": dev2.id, "analyst_id": analyst.id}


def _phase_assignment(db_session, plan_id: str, phase: str):
    from app.models import ResourcePlanAssignment

    return (
        db_session.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.phase == phase,
            )
            .limit(1)
        )
        .scalars()
        .first()
    )


def test_patch_assignment_start_date_pins_and_records_edit(
    client, db_session, ready_plan
):
    a = _phase_assignment(db_session, ready_plan["plan_id"], "analyst")
    assert a is not None
    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{ready_plan['plan_id']}/assignments/{a.id}",
        json={"start_date": "2026-05-01"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["start_date"] == "2026-05-01"
    assert body["is_pinned"] is True


def test_patch_assignment_employee_pins_employee(client, db_session, ready_plan):
    a = _phase_assignment(db_session, ready_plan["plan_id"], "dev")
    assert a is not None
    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{ready_plan['plan_id']}/assignments/{a.id}",
        json={"employee_id": ready_plan["alt_employee_id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["employee_id"] == ready_plan["alt_employee_id"]
    assert body["is_pinned"] is True


def test_patch_assignment_predecessors_replaces_edges(client, db_session, ready_plan):
    from app.models import PhasePredecessor, ResourcePlanAssignment

    qa = _phase_assignment(db_session, ready_plan["plan_id"], "qa")
    analyst = _phase_assignment(db_session, ready_plan["plan_id"], "analyst")
    assert qa and analyst

    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{ready_plan['plan_id']}/assignments/{qa.id}",
        json={"predecessor_ids": [analyst.id]},
    )
    assert r.status_code == 200, r.text

    rows = (
        db_session.execute(
            select(PhasePredecessor).where(
                PhasePredecessor.successor_assignment_id == qa.id
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].predecessor_assignment_id == analyst.id


def test_patch_assignment_predecessor_cycle_rejected(client, db_session, ready_plan):
    a = _phase_assignment(db_session, ready_plan["plan_id"], "analyst")
    b = _phase_assignment(db_session, ready_plan["plan_id"], "dev")
    assert a and b

    r1 = client.patch(
        f"/api/v1/resource-planning/resource-plans/{ready_plan['plan_id']}/assignments/{b.id}",
        json={"predecessor_ids": [a.id]},
    )
    assert r1.status_code == 200, r1.text

    r2 = client.patch(
        f"/api/v1/resource-planning/resource-plans/{ready_plan['plan_id']}/assignments/{a.id}",
        json={"predecessor_ids": [b.id]},
    )
    assert r2.status_code == 400
    assert "cycle" in r2.json()["detail"].lower()
