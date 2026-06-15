"""Интеграционные тесты публичного desk endpoint (GET /api/v1/desk/{token})."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Employee, EmployeeTeam
from app.services.work_desk_service import WorkDeskService


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
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def seed_employee(db_session):
    emp = Employee(
        id="emp-desk-1",
        jira_account_id="acc-desk-1",
        display_name="Стол Аналитик",
        avatar_url="https://example.com/a.png",
        is_active=True,
        synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(id="et-1", employee_id=emp.id, team="Alpha", is_primary=True))
    db_session.commit()
    return emp


def test_meta_valid_token(client, db_session, seed_employee):
    desk = WorkDeskService().create(db_session, seed_employee.id, ["hours_balance"], "usr-1")
    r = client.get(f"/api/v1/desk/{desk.token}")
    assert r.status_code == 200
    body = r.json()
    assert body["employee"]["display_name"] == seed_employee.display_name
    assert body["enabled_widgets"] == ["hours_balance"]
    assert body["teams"] == ["Alpha"]
    assert body["period"]["year"] >= 2026
    assert 1 <= body["period"]["quarter"] <= 4


def test_meta_updates_last_viewed(client, db_session, seed_employee):
    desk = WorkDeskService().create(db_session, seed_employee.id, [], "usr-1")
    assert desk.last_viewed_at is None
    client.get(f"/api/v1/desk/{desk.token}")
    db_session.refresh(desk)
    assert desk.last_viewed_at is not None


def test_meta_unknown_token_404(client):
    assert client.get("/api/v1/desk/nope").status_code == 404


def test_meta_revoked_token_404(client, db_session, seed_employee):
    svc = WorkDeskService()
    desk = svc.create(db_session, seed_employee.id, [], "usr-1")
    svc.revoke(db_session, desk.id)
    assert client.get(f"/api/v1/desk/{desk.token}").status_code == 404
