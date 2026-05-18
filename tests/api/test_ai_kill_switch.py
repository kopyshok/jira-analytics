"""Глобальный AI kill switch — backend-side gating."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.llm.base import is_ai_enabled


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


def _set_ai(client: TestClient, enabled: bool) -> None:
    r = client.put(
        "/api/v1/settings/generic",
        json={"key": "ai_enabled", "value": "true" if enabled else "false"},
    )
    assert r.status_code in (200, 204)


def test_is_ai_enabled_default_false(test_db_session):
    """Без записи в AppSetting — рубильник выключен."""
    assert is_ai_enabled(test_db_session) is False


def test_is_ai_enabled_true_when_set(test_client, test_db_session):
    _set_ai(test_client, True)
    assert is_ai_enabled(test_db_session) is True


def test_ai_status_endpoint(test_client):
    """GET /ai-status возвращает enabled-флаг."""
    r = test_client.get("/api/v1/ai-status")
    assert r.status_code == 200
    assert r.json() == {"enabled": False}
    _set_ai(test_client, True)
    r2 = test_client.get("/api/v1/ai-status")
    assert r2.json() == {"enabled": True}


def test_llm_test_blocked_when_off(test_client):
    """POST /llm/test → 503 когда выключено."""
    r = test_client.post("/api/v1/llm/test")
    assert r.status_code == 503
    assert "disabled" in r.json()["detail"].lower()


def test_llm_regenerate_all_blocked_when_off(test_client):
    r = test_client.post("/api/v1/llm/regenerate-all")
    assert r.status_code == 503


def test_llm_gemini_models_blocked_when_off(test_client):
    r = test_client.get("/api/v1/llm/gemini/models")
    assert r.status_code == 503


def test_llm_openrouter_models_blocked_when_off(test_client):
    r = test_client.get("/api/v1/llm/openrouter/models")
    assert r.status_code == 503


def test_project_regenerate_summary_blocked_when_off(test_client):
    r = test_client.post("/api/v1/projects/SOME-1/regenerate-summary")
    assert r.status_code == 503


def test_work_type_report_build_blocked_when_off(test_client):
    """POST /work-type-report → 503 когда AI выключен (ещё до валидации payload)."""
    r = test_client.post(
        "/api/v1/work-type-report",
        json={"work_type_id": "x", "year": 2026, "quarter": 1, "teams": []},
    )
    assert r.status_code == 503


def test_work_type_report_candidates_accept_blocked_when_off(test_client):
    r = test_client.post(
        "/api/v1/work-type-report/candidates/accept",
        json={"snapshot_id": "x", "proposed_name": "Foo"},
    )
    assert r.status_code == 503


def test_executive_build_blocked_when_off(test_client):
    r = test_client.post(
        "/api/v1/executive/dashboard/build",
        json={"year": 2026, "quarter": 1, "teams": []},
    )
    assert r.status_code == 503


def test_project_get_summary_NOT_blocked_when_off(test_client):
    """GET /projects/{key}/summary — кэш доступен даже когда AI выключен."""
    r = test_client.get("/api/v1/projects/UNKNOWN-KEY/summary")
    assert r.status_code == 200
    assert r.json() is None


def test_cron_regenerate_skips_when_off(test_db_session, monkeypatch):
    """Cron job не должен дергать provider если AI выключен."""
    import asyncio
    from app.jobs import regenerate_summaries

    called = {"flag": False}

    class FakeSvc:
        def __init__(self, db):
            pass

        async def regenerate(self, key):  # pragma: no cover — не должен вызваться
            called["flag"] = True

    monkeypatch.setattr(regenerate_summaries, "ProjectSummaryService", FakeSvc)
    monkeypatch.setattr(regenerate_summaries, "SessionLocal", lambda: test_db_session)

    stats = asyncio.run(regenerate_summaries.regenerate_outdated_summaries())
    assert stats.get("ai_disabled") is True
    assert called["flag"] is False
