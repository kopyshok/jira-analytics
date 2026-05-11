"""Тест GET /api/v1/planning/scenarios/{id}/continuation-info."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    BacklogItem,
    Employee,
    Issue,
    PlanningScenario,
    Project,
    ScenarioAllocation,
    Worklog,
)


@pytest.fixture
def db_session():
    """Local override: StaticPool, чтобы TestClient разделял соединение с тестом."""
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


def test_continuation_info_returns_map_with_subtree_spent(db_session, client):
    """Если у инициативы есть worklogs в Q1 на детях — endpoint их находит."""
    # Project + initiative
    proj = Project(jira_project_id="P1", key="ITL", name="ITL")
    db_session.add(proj); db_session.flush()
    initiative = Issue(
        jira_issue_id="J-1", key="ITL-299", project_id=proj.id,
        summary="ERP", issue_type="Initiative", status="In Progress",
    )
    db_session.add(initiative); db_session.flush()
    subtask = Issue(
        jira_issue_id="J-2", key="ITL-300", project_id=proj.id,
        summary="sub", issue_type="Task", status="Done",
        parent_id=initiative.id, assigned_category="analysis",
    )
    db_session.add(subtask); db_session.flush()
    emp = Employee(jira_account_id="acc", display_name="E", is_active=True)
    db_session.add(emp); db_session.flush()
    wl = Worklog(
        jira_worklog_id="w1", issue_id=subtask.id, employee_id=emp.id,
        started_at=datetime(2026, 2, 15), hours=20, time_spent_seconds=72000,
    )
    db_session.add(wl)
    sc = PlanningScenario(name="S", year=2026, quarter="Q2", status="draft")
    db_session.add(sc); db_session.flush()
    bi = BacklogItem(title="ITL-299", issue_id=initiative.id, estimate_analyst_hours=40)
    db_session.add(bi); db_session.flush()
    alloc = ScenarioAllocation(scenario_id=sc.id, backlog_item_id=bi.id, included_flag=True)
    db_session.add(alloc); db_session.commit()

    resp = client.get(f"/api/v1/planning/scenarios/{sc.id}/continuation-info")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    row = data["info_by_allocation_id"][alloc.id]
    assert row["is_continuation"] is True
    assert row["spent"]["analyst"] == 20.0
    assert row["spent_total"] == 20.0


def test_continuation_info_unknown_scenario_returns_empty(client):
    resp = client.get(
        "/api/v1/planning/scenarios/00000000-0000-0000-0000-000000000000/continuation-info"
    )
    assert resp.status_code == 200
    assert resp.json() == {"info_by_allocation_id": {}}
