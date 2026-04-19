"""Тесты PATCH /employees/{id} (частичное обновление — поле role)."""

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
                 is_active=True)
    db_session.add(e)
    db_session.commit()
    return e


def test_patch_role_sets_valid_role(client, employee, db_session):
    res = client.patch(f"/api/v1/employees/{employee.id}", json={"role": "analyst"})
    assert res.status_code == 200
    assert res.json()["role"] == "analyst"
    db_session.refresh(employee)
    assert employee.role == "analyst"


def test_patch_role_clears_with_null(client, employee, db_session):
    employee.role = "programmer"
    db_session.commit()

    res = client.patch(f"/api/v1/employees/{employee.id}", json={"role": None})
    assert res.status_code == 200
    assert res.json()["role"] is None
    db_session.refresh(employee)
    assert employee.role is None


def test_patch_role_rejects_unknown_value(client, employee):
    res = client.patch(f"/api/v1/employees/{employee.id}", json={"role": "ceo"})
    assert res.status_code == 422
    assert "Unknown role" in res.json()["detail"]


def test_patch_employee_missing_404(client):
    res = client.patch("/api/v1/employees/does-not-exist", json={"role": "analyst"})
    assert res.status_code == 404
