"""Тесты PUT /employees/{id}/team."""

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.database import get_db
from app.models import Employee


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
    e = Employee(id="emp1", jira_account_id="a1", display_name="Иванов",
                 is_active=True, team=None)
    db_session.add(e)
    db_session.commit()
    return e


def test_set_team(client, employee, db_session):
    db_session.query(Employee).first()  # pin :memory: connection
    r = client.put(f"/api/v1/employees/{employee.id}/team", json={"team": "Alpha"})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.get(Employee, employee.id).team == "Alpha"


def test_clear_team(client, employee, db_session):
    db_session.query(Employee).first()
    employee.team = "Alpha"
    db_session.commit()
    r = client.put(f"/api/v1/employees/{employee.id}/team", json={"team": None})
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.get(Employee, employee.id).team is None


def test_404_on_missing(client, db_session):
    db_session.query(Employee).first()
    r = client.put("/api/v1/employees/does-not-exist/team", json={"team": "Alpha"})
    assert r.status_code == 404
