"""Tests for subtracts_from_pool field on /mandatory-work-types API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db


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


def test_work_type_get_includes_subtracts_from_pool(client, db_session):
    """GET list returns subtracts_from_pool field."""
    client.post(
        "/api/v1/mandatory-work-types",
        json={"code": "wt_get", "label": "Get Test"},
    )
    r = client.get("/api/v1/mandatory-work-types")
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    for item in items:
        assert "subtracts_from_pool" in item
        assert item["subtracts_from_pool"] is True


def test_work_type_toggle(client, db_session):
    """PATCH can toggle subtracts_from_pool to False."""
    created = client.post(
        "/api/v1/mandatory-work-types",
        json={"code": "wt_toggle", "label": "Toggle Test"},
    )
    assert created.status_code == 201
    wt_id = created.json()["id"]
    resp = client.patch(
        f"/api/v1/mandatory-work-types/{wt_id}",
        json={"subtracts_from_pool": False},
    )
    assert resp.status_code == 200
    assert resp.json()["subtracts_from_pool"] is False


def test_work_type_create_with_subtracts_from_pool(client, db_session):
    """POST create respects subtracts_from_pool=False."""
    resp = client.post(
        "/api/v1/mandatory-work-types",
        json={"code": "test_wt", "label": "Test WT", "subtracts_from_pool": False},
    )
    assert resp.status_code == 201
    assert resp.json()["subtracts_from_pool"] is False


def test_work_type_create_default_subtracts_from_pool(client, db_session):
    """POST create defaults subtracts_from_pool to True when omitted."""
    resp = client.post(
        "/api/v1/mandatory-work-types",
        json={"code": "test_wt2", "label": "Test WT 2"},
    )
    assert resp.status_code == 201
    assert resp.json()["subtracts_from_pool"] is True
