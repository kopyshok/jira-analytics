"""Integration tests for /employees/{id}/teams endpoints."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Employee


@pytest.fixture
def db_session():
    """StaticPool session so Starlette worker threads share the same :memory: DB."""
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


@pytest.fixture
def emp(db_session):
    e = Employee(
        id="emp-1", jira_account_id="acc-1", display_name="Test",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(e)
    db_session.commit()
    return e


def test_get_teams_empty(client, emp):
    resp = client.get(f"/api/v1/employees/{emp.id}/teams")
    assert resp.status_code == 200
    assert resp.json() == []


def test_post_team_first_is_primary(client, emp):
    resp = client.post(
        f"/api/v1/employees/{emp.id}/teams", json={"team": "Alpha"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["team"] == "Alpha"
    assert body["is_primary"] is True


def test_put_teams_replaces_and_sets_primary(client, emp):
    resp = client.put(
        f"/api/v1/employees/{emp.id}/teams",
        json={"teams": ["A", "B", "C"], "primary": "B"},
    )
    assert resp.status_code == 200
    body = resp.json()
    names = {r["team"] for r in body}
    assert names == {"A", "B", "C"}
    primaries = [r for r in body if r["is_primary"]]
    assert len(primaries) == 1
    assert primaries[0]["team"] == "B"


def test_delete_team(client, emp):
    client.post(f"/api/v1/employees/{emp.id}/teams", json={"team": "A"})
    client.post(f"/api/v1/employees/{emp.id}/teams", json={"team": "B"})
    resp = client.delete(f"/api/v1/employees/{emp.id}/teams/A")
    assert resp.status_code == 204
    remaining = client.get(f"/api/v1/employees/{emp.id}/teams").json()
    assert [r["team"] for r in remaining] == ["B"]
    assert remaining[0]["is_primary"] is True


def test_put_primary(client, emp):
    client.put(
        f"/api/v1/employees/{emp.id}/teams",
        json={"teams": ["A", "B"], "primary": "A"},
    )
    resp = client.put(
        f"/api/v1/employees/{emp.id}/teams/primary", json={"team": "B"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert next(r for r in body if r["team"] == "B")["is_primary"] is True
    assert next(r for r in body if r["team"] == "A")["is_primary"] is False


def test_put_primary_unknown_team_404(client, emp):
    client.post(f"/api/v1/employees/{emp.id}/teams", json={"team": "A"})
    resp = client.put(
        f"/api/v1/employees/{emp.id}/teams/primary", json={"team": "Nope"}
    )
    assert resp.status_code == 404


def test_list_employees_with_teams(client, emp):
    client.put(
        f"/api/v1/employees/{emp.id}/teams",
        json={"teams": ["A", "B"], "primary": "B"},
    )
    resp = client.get("/api/v1/employees?with_teams=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["teams"] == [
        {"team": "B", "is_primary": True},
        {"team": "A", "is_primary": False},
    ]


def test_legacy_put_team_still_works(client, emp):
    resp = client.put(
        f"/api/v1/employees/{emp.id}/team", json={"team": "Legacy"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["team"] == "Legacy"
    teams = client.get(f"/api/v1/employees/{emp.id}/teams").json()
    assert teams == [{"team": "Legacy", "is_primary": True}]
    assert body.get("teams") is None


def test_list_employees_without_with_teams_has_null_teams(client, emp):
    client.put(
        f"/api/v1/employees/{emp.id}/teams",
        json={"teams": ["A"], "primary": "A"},
    )
    resp = client.get("/api/v1/employees")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0].get("teams") is None
