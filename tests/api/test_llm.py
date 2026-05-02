"""API /llm/test endpoint."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db


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


def test_llm_test_returns_400_without_key(test_client, test_db_session):
    """Без сконфигурированного API key возвращает 400."""
    r = test_client.post("/api/v1/llm/test")
    assert r.status_code == 400
    assert "not configured" in r.json()["detail"].lower()


def test_llm_settings_keys_accepted(test_client):
    """LLM-ключи проходят allow-list для /settings/generic."""
    r = test_client.put(
        "/api/v1/settings/generic",
        json={"key": "llm_provider", "value": "gemini"},
    )
    assert r.status_code in (200, 204)
    r2 = test_client.put(
        "/api/v1/settings/generic",
        json={"key": "llm_gemini_api_key", "value": "AIza-fake-test"},
    )
    assert r2.status_code in (200, 204)
