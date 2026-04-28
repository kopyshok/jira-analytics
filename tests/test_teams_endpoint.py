"""Integration tests for GET /api/v1/teams (distinct teams from local DB)."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Employee, EmployeeTeam, Issue, Project


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
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_teams_empty(client):
    resp = client.get("/api/v1/teams")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_teams_merges_issue_and_membership_sources(client, db_session):
    project = Project(
        id="prj-1", jira_project_id="10001", key="X", name="X",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(project)
    db_session.add(Issue(
        id="iss-1", jira_issue_id="100", key="X-1", summary="s",
        issue_type="Task", status="Open", project_id=project.id,
        team="Alpha", synced_at=datetime.utcnow(),
    ))
    db_session.add(Issue(
        id="iss-2", jira_issue_id="101", key="X-2", summary="s",
        issue_type="Task", status="Open", project_id=project.id,
        team="Beta", synced_at=datetime.utcnow(),
    ))
    db_session.add(Issue(
        id="iss-3", jira_issue_id="102", key="X-3", summary="s",
        issue_type="Task", status="Open", project_id=project.id,
        team=None, synced_at=datetime.utcnow(),
    ))
    emp = Employee(
        id="emp-1", jira_account_id="acc-1", display_name="E",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id="et-1", employee_id=emp.id, team="Beta", is_primary=True,
    ))
    db_session.add(EmployeeTeam(
        id="et-2", employee_id=emp.id, team="Gamma", is_primary=False,
    ))
    db_session.commit()

    resp = client.get("/api/v1/teams")
    assert resp.status_code == 200
    assert resp.json() == ["Alpha", "Beta", "Gamma"]
