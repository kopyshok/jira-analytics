"""API периодов участия в команде и перевода между командами."""

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
        jira_account_id="acc-1", display_name="Иванов И.",
        is_active=True, role="dev",
    )
    db_session.add(e)
    db_session.commit()
    return e


def test_patch_left_at(client, employee):
    """Проставить дату выбытия."""
    r = client.post(f"/api/v1/employees/{employee.id}/teams", json={"team": "Альфа"})
    assert r.status_code == 200, r.text

    r = client.patch(
        f"/api/v1/employees/{employee.id}/teams/Альфа/left-at",
        json={"left_at": "2026-02-15"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["left_at"] == "2026-02-15"


def test_patch_left_at_before_joined_at_422(client, employee):
    """Выбытие раньше входа — отказ."""
    client.post(f"/api/v1/employees/{employee.id}/teams", json={"team": "Альфа"})
    client.patch(
        f"/api/v1/employees/{employee.id}/teams/Альфа/joined-at",
        json={"joined_at": "2026-03-01"},
    )

    r = client.patch(
        f"/api/v1/employees/{employee.id}/teams/Альфа/left-at",
        json={"left_at": "2026-02-01"},
    )
    assert r.status_code == 422, r.text


def test_transfer_endpoint(client, employee):
    """Перевод закрывает старое участие и открывает новое."""
    client.post(f"/api/v1/employees/{employee.id}/teams", json={"team": "Альфа"})

    r = client.post(
        f"/api/v1/employees/{employee.id}/teams/transfer",
        json={"from_team": "Альфа", "to_team": "Бета", "on": "2026-02-15"},
    )
    assert r.status_code == 200, r.text
    rows = {x["team"]: x for x in r.json()}
    assert rows["Альфа"]["left_at"] == "2026-02-15"
    assert rows["Бета"]["joined_at"] == "2026-02-15"
    assert rows["Бета"]["is_primary"] is True


def test_transfer_unknown_team_404(client, employee):
    """Перевод из команды, где человек не состоит."""
    r = client.post(
        f"/api/v1/employees/{employee.id}/teams/transfer",
        json={"from_team": "Гамма", "to_team": "Бета", "on": "2026-02-15"},
    )
    assert r.status_code == 404, r.text
