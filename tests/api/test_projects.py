"""API /projects: list + detail."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.issue import Issue
from app.models.project import Project
from app.models.worklog import Worklog
from app.models.employee import Employee


@pytest.fixture
def test_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def test_client(test_db_session):
    def _get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed(db):
    db.add(Project(id="p1", jira_project_id="10001", key="PRJ", name="Project"))
    db.add(Issue(id="ip", jira_issue_id="100", key="PRJ-100", summary="Quarterly One",
                 issue_type="Epic", status="Done", project_id="p1",
                 category="quarterly_tasks", include_in_analysis=True,
                 rating_quality=5, rating_speed=4, rating_result=5))
    db.add(Issue(id="ic", jira_issue_id="101", key="PRJ-101", summary="Child",
                 issue_type="Task", status="Done", project_id="p1",
                 parent_id="ip", category="tech_debt", include_in_analysis=True))
    db.add(Issue(id="ix", jira_issue_id="200", key="PRJ-200", summary="Tech Debt",
                 issue_type="Epic", status="Done", project_id="p1",
                 category="tech_debt", include_in_analysis=True))
    db.add(Employee(id="e1", jira_account_id="acc1", display_name="A", email="a@e", is_active=True, team="T"))
    db.add(Worklog(id="w1", jira_worklog_id="w1", issue_id="ic", employee_id="e1",
                   hours=10, time_spent_seconds=36000,
                   started_at=datetime(2026, 2, 1), updated_at=datetime(2026, 2, 1)))
    db.commit()


def test_list_projects_returns_only_quarterly(test_client, test_db_session):
    _seed(test_db_session)
    r = test_client.get("/api/v1/projects")
    assert r.status_code == 200
    keys = {p["key"] for p in r.json()}
    assert "PRJ-100" in keys
    assert "PRJ-200" not in keys


def test_get_project_detail_ok(test_client, test_db_session):
    _seed(test_db_session)
    r = test_client.get("/api/v1/projects/PRJ-100")
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "PRJ-100"
    assert body["total_hours"] == 10.0
    assert body["rating_quality"] == 5
    assert len(body["employees"]) == 1


def test_get_project_detail_404_for_non_quarterly(test_client, test_db_session):
    _seed(test_db_session)
    r = test_client.get("/api/v1/projects/PRJ-200")
    assert r.status_code == 404
    r2 = test_client.get("/api/v1/projects/UNKNOWN")
    assert r2.status_code == 404
