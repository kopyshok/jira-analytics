"""Tests for POST /sync/worklogs/reload endpoint."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import AppSetting
from app.services.sync_service import ReloadStats


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@asynccontextmanager
async def _fake_jira_ctx(*args, **kwargs):
    """Stand-in for ``async with JiraClient.from_db(db)`` that skips
    credential/httpx setup — the service method is patched anyway."""
    yield object()


def test_post_reload_persists_since_and_returns_stats(client, db_session):
    # Pin the session's connection to the test thread before the endpoint
    # touches it. SingletonThreadPool + :memory: gives each thread its own
    # empty DB on connect; pre-querying here makes the Session cache the
    # already-populated connection so the handler reuses it.
    db_session.query(AppSetting).first()

    stats = ReloadStats(deleted=5, issues_scanned=3, worklogs_inserted=7)

    with patch(
        "app.api.endpoints.sync.JiraClient.from_db",
        return_value=_fake_jira_ctx(),
    ), patch(
        "app.services.sync_service.SyncService.reload_worklogs_since",
        new=AsyncMock(return_value=stats),
    ):
        resp = client.post(
            "/api/v1/sync/worklogs/reload", json={"since": "2026-01-01"}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"deleted": 5, "issues_scanned": 3, "worklogs_inserted": 7}

    setting = (
        db_session.query(AppSetting)
        .filter(AppSetting.key == "worklog_reload_since_date")
        .one_or_none()
    )
    assert setting is not None
    assert setting.value == "2026-01-01"


def test_post_reload_rejects_invalid_date(client):
    resp = client.post(
        "/api/v1/sync/worklogs/reload", json={"since": "not-a-date"}
    )
    assert resp.status_code == 422
