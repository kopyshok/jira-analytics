"""Снимок утверждения и расхождение состава после выбытия."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
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


def test_departure_after_approval_shows_drift(client, db_session):
    """Выбытие после утверждения → расхождение видно, слепок не изменился."""
    emp = Employee(
        jira_account_id="acc-1", display_name="Иванов И.",
        is_active=True, role="dev",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Альфа", is_primary=True))
    db_session.commit()

    r = client.post("/api/v1/planning/scenarios", json={
        "name": "Q1", "year": 2026, "quarter": 1, "team": "Альфа",
    })
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    r = client.post(f"/api/v1/planning/scenarios/{sid}/approve")
    assert r.status_code == 200, r.text

    # До выбытия расхождения нет
    r = client.get(f"/api/v1/planning/scenarios/{sid}/capacity-diff")
    assert r.status_code == 200, r.text
    assert r.json()["has_changes"] is False

    # Выбытие в середине квартала
    r = client.patch(
        f"/api/v1/employees/{emp.id}/teams/Альфа/left-at",
        json={"left_at": "2026-02-15"},
    )
    assert r.status_code == 200, r.text

    r = client.get(f"/api/v1/planning/scenarios/{sid}/capacity-diff")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_changes"] is True
    changed = body["changed_employees"][0]
    assert changed["employee_id"] == emp.id
    assert changed["left_team_at"] == "2026-02-15"
    # Часы после выбытия обнулились, до выбытия — нет
    by_month = {m["month"]: m for m in changed["months"]}
    assert by_month[3]["current_available_hours"] == 0.0
    assert by_month[3]["delta_hours"] < 0
