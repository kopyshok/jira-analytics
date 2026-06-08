"""Tests for POST /sync/worklogs/reload endpoint."""

import json
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
        "app.services.sync_service.SyncService.reload_worklogs_v2_bulk",
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


def _parse_sse(raw: str) -> list[dict]:
    """Разобрать ``text/event-stream`` в список JSON-событий.

    Формат: каждое событие — блок строк, разделённый ``\\n\\n``;
    строка данных начинается с ``data:``.
    """
    events: list[dict] = []
    for block in raw.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data:"):
                events.append(json.loads(line.removeprefix("data:").strip()))
    return events


def test_post_reload_stream_emits_progress_and_done(client, db_session):
    db_session.query(AppSetting).first()

    async def fake_reload(self, since, on_progress=None):
        stats = ReloadStats(deleted=2)
        if on_progress is not None:
            await on_progress(stats, None)
        stats.issues_scanned = 1
        stats.worklogs_inserted = 3
        if on_progress is not None:
            await on_progress(stats, "PRJ-1")
        stats.issues_scanned = 2
        stats.worklogs_inserted = 5
        if on_progress is not None:
            await on_progress(stats, "PRJ-2")
        return stats

    with patch(
        "app.api.endpoints.sync.JiraClient.from_db",
        return_value=_fake_jira_ctx(),
    ), patch(
        "app.services.sync_service.SyncService.reload_worklogs_v2_bulk",
        new=fake_reload,
    ):
        with client.stream(
            "POST",
            "/api/v1/sync/worklogs/reload/stream",
            json={"since": "2026-02-01"},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = resp.read().decode("utf-8")

    events = _parse_sse(body)
    types = [e["type"] for e in events]
    assert types[0] == "progress"
    assert types[-1] == "done"
    assert "progress" in types[1:-1] or types[1] == "progress"

    done = events[-1]
    assert done == {
        "type": "done",
        "deleted": 2,
        "issues_scanned": 2,
        "worklogs_inserted": 5,
    }

    progress_with_key = [e for e in events if e["type"] == "progress" and e.get("current_key")]
    assert any(e["current_key"] == "PRJ-2" for e in progress_with_key)

    setting = (
        db_session.query(AppSetting)
        .filter(AppSetting.key == "worklog_reload_since_date")
        .one_or_none()
    )
    assert setting is not None
    assert setting.value == "2026-02-01"
