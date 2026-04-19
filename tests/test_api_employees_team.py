"""Тесты PUT /employees/{id}/team."""

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
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
    r = client.put(f"/api/v1/employees/{employee.id}/team", json={"team": "Alpha"})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.get(Employee, employee.id).team == "Alpha"


def test_clear_team(client, employee, db_session):
    employee.team = "Alpha"
    db_session.commit()
    r = client.put(f"/api/v1/employees/{employee.id}/team", json={"team": None})
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.get(Employee, employee.id).team is None


def test_404_on_missing(client, db_session):
    r = client.put("/api/v1/employees/does-not-exist/team", json={"team": "Alpha"})
    assert r.status_code == 404
