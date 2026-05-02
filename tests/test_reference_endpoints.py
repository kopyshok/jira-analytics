"""Reference-data endpoint tests."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Employee, Project


@pytest.fixture
def client(db_session):
    """Test client bound to the in-memory database session."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_employees_filters_by_active_flag(client, db_session):
    db_session.add_all(
        [
            Employee(
                jira_account_id="active-1",
                display_name="Active User",
                is_active=True,
            ),
            Employee(
                jira_account_id="inactive-1",
                display_name="Inactive User",
                is_active=False,
            ),
        ]
    )
    db_session.flush()

    response = client.get("/api/v1/employees?is_active=true")

    assert response.status_code == 200
    assert [row["display_name"] for row in response.json()] == ["Active User"]


def test_list_projects_filters_by_active_flag(client, db_session):
    db_session.add_all(
        [
            Project(
                jira_project_id="10001",
                key="ACT",
                name="Active Project",
                is_active=True,
            ),
            Project(
                jira_project_id="10002",
                key="OLD",
                name="Inactive Project",
                is_active=False,
            ),
        ]
    )
    db_session.flush()

    response = client.get("/api/v1/projects/all?is_active=true")

    assert response.status_code == 200
    assert [row["key"] for row in response.json()] == ["ACT"]
