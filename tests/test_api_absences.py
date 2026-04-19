"""Тесты API /capacity/absences."""

from datetime import date
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.database import get_db
from app.models import Absence, Employee


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def employee(db_session):
    e = Employee(
        id="emp1", jira_account_id="a1", display_name="Иванов И.",
        is_active=True,
    )
    db_session.add(e)
    db_session.commit()
    return e


def test_list_empty(client, db_session):
    db_session.query(Employee).first()  # pin :memory: connection to test thread
    r = client.get("/api/v1/capacity/absences")
    assert r.status_code == 200
    assert r.json() == []


def test_create_with_reason_sick(client, employee, db_session):
    db_session.query(Employee).first()  # pin :memory: connection to test thread
    payload = {
        "employee_id": employee.id,
        "start_date": "2026-04-10",
        "end_date": "2026-04-12",
        "reason": "sick",
    }
    r = client.post("/api/v1/capacity/absences", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["reason"] == "sick"
    assert body["start_date"] == "2026-04-10"
    row = db_session.query(Absence).one()
    assert row.reason == "sick"


def test_create_defaults_reason_to_vacation(client, employee, db_session):
    db_session.query(Employee).first()  # pin :memory: connection to test thread
    payload = {
        "employee_id": employee.id,
        "start_date": "2026-04-10",
        "end_date": "2026-04-12",
    }
    r = client.post("/api/v1/capacity/absences", json=payload)
    assert r.status_code == 201
    assert r.json()["reason"] == "vacation"


def test_create_rejects_unknown_reason(client, employee):
    payload = {
        "employee_id": employee.id,
        "start_date": "2026-04-10",
        "end_date": "2026-04-12",
        "reason": "bogus",
    }
    r = client.post("/api/v1/capacity/absences", json=payload)
    assert r.status_code == 422


def test_create_rejects_inverted_dates(client, employee):
    payload = {
        "employee_id": employee.id,
        "start_date": "2026-04-12",
        "end_date": "2026-04-10",
        "reason": "vacation",
    }
    r = client.post("/api/v1/capacity/absences", json=payload)
    assert r.status_code == 400


def test_delete(client, employee, db_session):
    a = Absence(
        id="a1", employee_id=employee.id,
        start_date=date(2026, 4, 10), end_date=date(2026, 4, 12), reason="vacation",
    )
    db_session.add(a)
    db_session.commit()
    r = client.delete(f"/api/v1/capacity/absences/{a.id}")
    assert r.status_code == 200
    assert db_session.query(Absence).count() == 0


def test_old_vacations_endpoints_are_gone(client, db_session):
    db_session.query(Employee).first()  # pin :memory: connection to test thread
    r = client.get("/api/v1/capacity/vacations")
    assert r.status_code == 404
