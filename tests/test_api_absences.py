"""Тесты API /capacity/absences."""

from datetime import date
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import Absence, Employee
from app.models.absence_reason import AbsenceReason


@pytest.fixture
def db_session():
    """Local StaticPool engine so the TestClient thread sees the same
    in-memory SQLite connection (the shared session-scoped engine in
    conftest.py uses the default pool which gives each thread its own
    empty :memory: DB)."""
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


@pytest.fixture
def employee(db_session):
    e = Employee(
        id="emp1", jira_account_id="a1", display_name="Иванов И.",
        is_active=True,
    )
    db_session.add(e)
    db_session.commit()
    return e


@pytest.fixture
def reasons(db_session):
    """Seed absence_reasons directory (migration 021 seeds these in prod;
    conftest wipes tables between tests, so we re-seed per test)."""
    rows = [
        AbsenceReason(id="reason-vacation", code="vacation", label="Отпуск",
                      is_planned=True, color="#fa8c16", sort_order=0),
        AbsenceReason(id="reason-sick", code="sick", label="Больничный",
                      is_planned=False, color="#f5222d", sort_order=1),
        AbsenceReason(id="reason-day_off", code="day_off", label="Отгул",
                      is_planned=False, color="#1677ff", sort_order=2),
        AbsenceReason(id="reason-other", code="other", label="Прочее",
                      is_planned=False, color="#8c8c8c", sort_order=3),
    ]
    for r in rows:
        db_session.add(r)
    db_session.commit()
    return {r.code: r for r in rows}


def test_list_empty(client, db_session):
    db_session.query(Employee).first()  # pin :memory: connection to test thread
    r = client.get("/api/v1/capacity/absences")
    assert r.status_code == 200
    assert r.json() == []


def test_create_with_reason_sick(client, employee, reasons, db_session):
    db_session.query(Employee).first()  # pin :memory: connection to test thread
    payload = {
        "employee_id": employee.id,
        "start_date": "2026-04-10",
        "end_date": "2026-04-12",
        "reason_id": "reason-sick",
    }
    r = client.post("/api/v1/capacity/absences", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["reason_id"] == "reason-sick"
    assert body["reason_code"] == "sick"
    assert body["reason_label"] == "Больничный"
    assert body["reason_is_planned"] is False
    assert body["start_date"] == "2026-04-10"
    row = db_session.query(Absence).one()
    assert row.reason_id == "reason-sick"


def test_create_with_vacation_reason(client, employee, reasons, db_session):
    db_session.query(Employee).first()  # pin :memory: connection to test thread
    payload = {
        "employee_id": employee.id,
        "start_date": "2026-04-10",
        "end_date": "2026-04-12",
        "reason_id": "reason-vacation",
    }
    r = client.post("/api/v1/capacity/absences", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["reason_id"] == "reason-vacation"
    assert body["reason_code"] == "vacation"
    assert body["reason_is_planned"] is True


def test_create_rejects_unknown_reason(client, employee, reasons):
    payload = {
        "employee_id": employee.id,
        "start_date": "2026-04-10",
        "end_date": "2026-04-12",
        "reason_id": "reason-bogus",
    }
    r = client.post("/api/v1/capacity/absences", json=payload)
    assert r.status_code == 422


def test_create_rejects_inverted_dates(client, employee, reasons):
    payload = {
        "employee_id": employee.id,
        "start_date": "2026-04-12",
        "end_date": "2026-04-10",
        "reason_id": "reason-vacation",
    }
    r = client.post("/api/v1/capacity/absences", json=payload)
    assert r.status_code == 400


def test_delete(client, employee, reasons, db_session):
    db_session.query(Employee).first()  # pin :memory: connection to test thread
    a = Absence(
        id="a1", employee_id=employee.id,
        start_date=date(2026, 4, 10), end_date=date(2026, 4, 12),
        reason_id="reason-vacation",
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
