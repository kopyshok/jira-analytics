"""Tests for PATCH /api/v1/employees/{id}/teams/{team}/joined-at."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam


@pytest.fixture
def client(testclient_db_session):
    def _get_db():
        yield testclient_db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app), testclient_db_session
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def seeded(testclient_db_session):
    emp = Employee(
        id="emp-jat-1",
        jira_account_id="jira-jat-1",
        display_name="Joined Test",
        is_active=True,
    )
    testclient_db_session.add(emp)
    et = EmployeeTeam(
        employee_id="emp-jat-1",
        team="TeamA",
        is_primary=True,
    )
    testclient_db_session.add(et)
    testclient_db_session.commit()
    return emp, et


def test_patch_joined_at_valid_date(client, seeded):
    tc, db = client
    r = tc.patch(
        "/api/v1/employees/emp-jat-1/teams/TeamA/joined-at",
        json={"joined_at": "2026-01-21"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["joined_at"] == "2026-01-21"
    assert body["team"] == "TeamA"
    assert body["is_primary"] is True


def test_patch_joined_at_null_clears(client, seeded):
    tc, db = client
    # Set a date first
    tc.patch(
        "/api/v1/employees/emp-jat-1/teams/TeamA/joined-at",
        json={"joined_at": "2026-01-21"},
    )
    # Now clear it
    r = tc.patch(
        "/api/v1/employees/emp-jat-1/teams/TeamA/joined-at",
        json={"joined_at": None},
    )
    assert r.status_code == 200
    assert r.json()["joined_at"] is None


def test_patch_joined_at_nonexistent_employee(client):
    tc, db = client
    r = tc.patch(
        "/api/v1/employees/no-such-id/teams/SomeTeam/joined-at",
        json={"joined_at": "2026-01-21"},
    )
    assert r.status_code == 404


def test_patch_joined_at_nonexistent_team(client, seeded):
    tc, db = client
    r = tc.patch(
        "/api/v1/employees/emp-jat-1/teams/NoSuchTeam/joined-at",
        json={"joined_at": "2026-01-21"},
    )
    assert r.status_code == 404
