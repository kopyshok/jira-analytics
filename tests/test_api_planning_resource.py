"""Tests for GET /planning/scenarios/{id}/resource endpoint."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Employee, EmployeeTeam, PlanningScenario, ProductionCalendarDay


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
        app.dependency_overrides.clear()


def _create_scenario(client, **kwargs):
    payload = {"name": "Test scenario", "year": 2026, "quarter": 1}
    payload.update(kwargs)
    r = client.post("/api/v1/planning/scenarios", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# test_scenario_resource_requires_team
# ---------------------------------------------------------------------------

def test_scenario_resource_requires_team(client, db_session):
    """GET /scenarios/{id}/resource → 400 когда у сценария нет команды."""
    scenario = _create_scenario(client, year=2026, quarter=1)
    # Нет команды — ожидаем 400.
    r = client.get(f"/api/v1/planning/scenarios/{scenario['id']}/resource")
    assert r.status_code == 400, r.text
    assert "Команда" in r.json()["detail"]


# ---------------------------------------------------------------------------
# test_scenario_resource_404_for_missing
# ---------------------------------------------------------------------------

def test_scenario_resource_404_for_missing(client, db_session):
    """GET /scenarios/{id}/resource → 404 для несуществующего сценария."""
    r = client.get("/api/v1/planning/scenarios/nonexistent-id/resource")
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# test_scenario_resource_returns_per_day
# ---------------------------------------------------------------------------

def test_scenario_resource_returns_per_day(client, db_session):
    """GET /scenarios/{id}/resource → 200 с посуточными данными по сотруднику."""
    # Сотрудник команды TeamA.
    emp = Employee(
        jira_account_id="jira-test-001",
        display_name="Test Employee",
        email="test@example.com",
        role="analyst",
        is_active=True,
    )
    db_session.add(emp)
    db_session.flush()

    db_session.add(EmployeeTeam(employee_id=emp.id, team="TeamA", is_primary=True))

    # Один рабочий день в производственном календаре (2026-01-05 — понедельник).
    db_session.add(
        ProductionCalendarDay(
            date=date(2026, 1, 5),
            hours=8.0,
            is_workday=True,
            kind="workday",
            source="manual",
        )
    )
    db_session.commit()

    # Сценарий с командой, годом и кварталом.
    scenario = _create_scenario(client, team="TeamA", year=2026, quarter=1)
    sid = scenario["id"]

    r = client.get(f"/api/v1/planning/scenarios/{sid}/resource")
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["year"] == 2026
    assert body["quarter"] == 1
    assert body["team"] == "TeamA"

    # Хотя бы один сотрудник.
    assert len(body["employees"]) >= 1
    emp_out = body["employees"][0]
    assert emp_out["employee_id"] == emp.id
    assert emp_out["role"] == "analyst"
    # Есть хотя бы один день.
    assert len(emp_out["days"]) >= 1
    # Формат даты — ISO строка.
    day0 = emp_out["days"][0]
    assert "date" in day0
    assert isinstance(day0["date"], str)
    assert len(day0["date"]) == 10  # YYYY-MM-DD
    assert isinstance(day0["hours"], float)

    # role_totals содержит роль сотрудника.
    assert "analyst" in body["role_totals"]
    assert body["role_totals"]["analyst"] > 0
