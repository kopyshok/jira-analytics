"""Тесты POST /capacity/team/recalc endpoint."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import Employee, EmployeeTeam


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


def _make_employee(db_session, jira_id: str, name: str, is_active: bool = True) -> Employee:
    emp = Employee(jira_account_id=jira_id, display_name=name, is_active=is_active)
    db_session.add(emp)
    db_session.flush()
    return emp


def _add_team(db_session, employee: Employee, team: str, is_primary: bool = True) -> None:
    membership = EmployeeTeam(employee_id=employee.id, team=team, is_primary=is_primary)
    db_session.add(membership)
    db_session.flush()


def test_team_recalc_updates_plan_hours(client, db_session):
    """Endpoint возвращает количество активных сотрудников команды."""
    # 2 active + 1 inactive in TeamA
    emp1 = _make_employee(db_session, "jira-001", "Alice", is_active=True)
    emp2 = _make_employee(db_session, "jira-002", "Bob", is_active=True)
    emp3 = _make_employee(db_session, "jira-003", "Inactive", is_active=False)
    _add_team(db_session, emp1, "TeamA")
    _add_team(db_session, emp2, "TeamA")
    _add_team(db_session, emp3, "TeamA")
    db_session.commit()

    resp = client.post(
        "/api/v1/capacity/team/recalc",
        params={"year": 2026, "quarter": 1, "team": "TeamA"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "updated_employees" in body
    assert body["updated_employees"] == 2
    assert body["year"] == 2026
    assert body["quarter"] == 1
    assert body["team"] == "TeamA"
    assert "recalculated_at" in body


def test_team_recalc_unknown_team_returns_zero(client, db_session):
    """Несуществующая команда возвращает 0, а не 404."""
    resp = client.post(
        "/api/v1/capacity/team/recalc",
        params={"year": 2026, "quarter": 2, "team": "NoSuchTeam"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated_employees"] == 0
    assert body["team"] == "NoSuchTeam"
