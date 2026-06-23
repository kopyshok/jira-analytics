"""Tests for PUT .../assignments/{id}/involvement — правка вовлечённости фазы.

Вовлечённость хранится на инициативе (BacklogItem) per-фаза. Эндпоинт пишет
involvement_<phase> и пересчитывает план, чтобы бары сразу обновились.
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
    from app.models import (
        BacklogItem,
        Employee,
        PlanningScenario,
        ResourcePlan,
        ScenarioAllocation,
    )
    from app.models.employee_team import EmployeeTeam
    from app.services.resource_planning_service import ResourcePlanningService

    team = "T_INV"
    analyst = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="Analyst",
        team=team,
        is_active=True,
        role="analyst",
    )
    db_session.add(analyst)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=analyst.id, team=team, is_primary=True))

    item = BacklogItem(
        title="inv-test",
        priority=1,
        estimate_analyst_hours=16.0,
        involvement_analyst=1.0,
        assignee_employee_id=analyst.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="inv-scenario", quarter="Q2", year=2026, status="draft", team=team
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(
        ScenarioAllocation(
            scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
        )
    )
    plan = ResourcePlan(
        team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id
    )
    db_session.add(plan)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)
    return {"plan_id": plan.id, "item_id": item.id}


def _analyst_assignment(db_session, plan_id: str):
    from app.models import ResourcePlanAssignment

    return (
        db_session.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.phase == "analyst",
            )
            .limit(1)
        )
        .scalars()
        .first()
    )


def test_put_involvement_writes_and_recomputes(client, db_session, ready_plan):
    from app.models import BacklogItem

    a = _analyst_assignment(db_session, ready_plan["plan_id"])
    assert a is not None

    r = client.put(
        f"/api/v1/resource-planning/resource-plans/{ready_plan['plan_id']}"
        f"/assignments/{a.id}/involvement",
        json={"involvement_pct": 70},
    )
    assert r.status_code == 200, r.text

    db_session.expire_all()
    item = db_session.get(BacklogItem, ready_plan["item_id"])
    assert item.involvement_analyst == pytest.approx(0.7, abs=0.001)


def test_put_involvement_rejects_out_of_range(client, db_session, ready_plan):
    a = _analyst_assignment(db_session, ready_plan["plan_id"])
    r = client.put(
        f"/api/v1/resource-planning/resource-plans/{ready_plan['plan_id']}"
        f"/assignments/{a.id}/involvement",
        json={"involvement_pct": 150},
    )
    assert r.status_code == 422
