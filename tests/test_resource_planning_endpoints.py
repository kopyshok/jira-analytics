"""Endpoint tests for resource planning — PATCH + Gantt projection fields."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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
def ready_plan(db_session, client):
    from app.models import BacklogItem, Employee, ResourcePlan, ResourcePlanAssignment
    from app.models.employee_team import EmployeeTeam
    from app.models.planning_scenario import PlanningScenario
    from app.models.scenario_allocation import ScenarioAllocation

    e1 = Employee(jira_account_id="jira-e1", display_name="Аналитик", role="analyst", team="T", is_active=True)
    e2 = Employee(jira_account_id="jira-e2", display_name="Разраб2", role="developer", team="T", is_active=True)
    db_session.add_all([e1, e2])
    db_session.commit()
    db_session.add_all([
        EmployeeTeam(employee_id=e1.id, team="T", is_primary=True),
        EmployeeTeam(employee_id=e2.id, team="T", is_primary=True),
    ])
    db_session.commit()

    item = BacklogItem(title="X", estimate_dev_hours=10, assignee_employee_id=e1.id)
    db_session.add(item)
    db_session.commit()

    # Scenario + allocation нужны, чтобы compute_schedule пересчитывал план
    # с реальными данными при смене сотрудника (а не удалял всё).
    scenario = PlanningScenario(name="T", quarter="Q2", year=2026, team="T", status="approved")
    db_session.add(scenario)
    db_session.commit()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True,
    ))
    db_session.commit()

    plan = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready", scenario_id=scenario.id)
    db_session.add(plan)
    db_session.commit()

    a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        employee_id=e1.id,
        hours_allocated=10,
    )
    db_session.add(a)
    db_session.commit()

    return plan.id, a.id, e2.id


def test_patch_assignment_sets_is_pinned(client, db_session, ready_plan):
    """PATCH с employee_id ставит is_pinned=True."""
    plan_id, assignment_id, dev2_id = ready_plan
    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{plan_id}/assignments/{assignment_id}",
        json={"employee_id": dev2_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_pinned"] is True
    assert body["employee_id"] == dev2_id


def test_gantt_response_includes_backlog_item_key(client, ready_plan):
    """GET /gantt отдаёт backlog_item_key (если есть Issue.key)."""
    plan_id, _, _ = ready_plan
    r = client.get(f"/api/v1/resource-planning/resource-plans/{plan_id}/gantt")
    assert r.status_code == 200
    proj = r.json()
    # backlog_item_key поле есть для каждого assignment (может быть None если issue нет)
    assert all("backlog_item_key" in a for a in proj["assignments"])


def test_gantt_response_includes_employee_role(client, ready_plan):
    plan_id, _, _ = ready_plan
    r = client.get(f"/api/v1/resource-planning/resource-plans/{plan_id}/gantt")
    proj = r.json()
    assert all("employee_role" in a for a in proj["assignments"])
