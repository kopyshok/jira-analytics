"""Тесты persistent conflict register API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import PlanConflict, ResourcePlan


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
        app.dependency_overrides.pop(get_db, None)


def test_patch_conflict_status_persists(client, db_session):
    plan = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    c = PlanConflict(
        plan_id=plan.id,
        type="OVERLOAD_HIGH",
        severity="critical",
        status="open",
        message="test",
        detection_key="test:1",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{plan.id}/conflicts/{c.id}",
        json={"status": "acknowledged"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "acknowledged"

    db_session.refresh(c)
    assert c.status == "acknowledged"


def test_patch_conflict_invalid_status_returns_422(client, db_session):
    plan = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    c = PlanConflict(
        plan_id=plan.id,
        type="OVERLOAD_HIGH",
        severity="critical",
        status="open",
        message="test",
        detection_key="test:1",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{plan.id}/conflicts/{c.id}",
        json={"status": "bogus"},
    )
    assert r.status_code == 422


def test_patch_conflict_unknown_returns_404(client, db_session):
    plan = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{plan.id}/conflicts/no-such-id",
        json={"status": "acknowledged"},
    )
    assert r.status_code == 404
