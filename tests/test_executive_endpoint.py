"""Executive dashboard endpoint tests."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session, monkeypatch):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db

    # No LLM provider — tests should hit fallback path.
    def _no_provider(_db):
        raise RuntimeError("no LLM in tests")
    monkeypatch.setattr(
        "app.api.endpoints.executive.get_llm_provider", _no_provider,
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_get_dashboard_404_when_no_snapshot(client):
    r = client.get("/api/v1/executive/dashboard?year=2026&quarter=2")
    assert r.status_code == 404


def test_post_build_then_get_returns_snapshot(client):
    """POST /build создаёт snapshot, GET его читает."""
    r = client.post(
        "/api/v1/executive/dashboard/build",
        json={"year": 2026, "quarter": 2, "teams": []},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "kpi" in data
    assert "ai_summary" in data
    assert data["ai_summary"]["is_fallback"] is True

    r2 = client.get("/api/v1/executive/dashboard?year=2026&quarter=2")
    assert r2.status_code == 200
    assert r2.json()["data"]["kpi"] == data["kpi"]
