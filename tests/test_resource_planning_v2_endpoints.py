"""Tests for /api/v1/resource-planning-v2 endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.resource_plan import ResourcePlan


@pytest.fixture
def test_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def test_client(test_db_session):
    def _get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_get_quality_returns_zeros_for_empty_plan(test_client: TestClient, test_db_session):
    plan = ResourcePlan(team="A", quarter="Q2", year=2026, status="ready")
    test_db_session.add(plan)
    test_db_session.commit()

    r = test_client.get(f"/api/v1/resource-planning-v2/{plan.id}/quality")
    assert r.status_code == 200
    body = r.json()
    assert body["plan_id"] == plan.id
    assert body["overload_days_pct"] == 0.0
    assert body["late_count"] == 0
    assert body["mean_utilization_pct"] == 0.0
    assert "computed_at" in body


def test_get_quality_404_for_unknown_plan(test_client: TestClient):
    r = test_client.get("/api/v1/resource-planning-v2/nonexistent/quality")
    assert r.status_code == 404


def test_optimize_501_until_implemented(test_client: TestClient, test_db_session):
    plan = ResourcePlan(team="A", quarter="Q2", year=2026, status="ready")
    test_db_session.add(plan)
    test_db_session.commit()

    r = test_client.post(f"/api/v1/resource-planning-v2/{plan.id}/optimize")
    assert r.status_code == 501  # удалится в Task 8
