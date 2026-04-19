"""Tests for POST /sync/worklogs/update/stream SSE endpoint."""

import json
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.services.sync_service import UpdateStats


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
    yield object()


def _parse_sse(raw: str) -> list[dict]:
    events: list[dict] = []
    for block in raw.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data:"):
                events.append(json.loads(line.removeprefix("data:").strip()))
    return events


def test_update_stream_emits_progress_and_done(client, db_session):
    from app.models import AppSetting
    db_session.query(AppSetting).first()  # pin session to thread

    async def fake_update(self, since, teams=None, on_progress=None):
        stats = UpdateStats(
            bucket_a_issues_scanned=1,
            bucket_a_worklogs_upserted=2,
        )
        if on_progress is not None:
            await on_progress(stats, "PRJ-1")
        stats.bucket_b_out_of_scope_created = 1
        stats.bucket_b_worklogs_upserted = 3
        if on_progress is not None:
            await on_progress(stats, "OTHER-1")
        return stats

    with patch(
        "app.api.endpoints.sync.JiraClient.from_db",
        return_value=_fake_jira_ctx(),
    ), patch(
        "app.services.sync_service.SyncService.update_worklogs_since",
        new=fake_update,
    ):
        with client.stream(
            "POST",
            "/api/v1/sync/worklogs/update/stream",
            json={"since": "2026-02-01", "teams": ["Alpha"]},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = resp.read().decode("utf-8")

    events = _parse_sse(body)
    types = [e["type"] for e in events]
    assert types[0] == "progress"
    assert types[-1] == "done"
    done = events[-1]
    assert done == {
        "type": "done",
        "bucket_a_issues_scanned": 1,
        "bucket_a_worklogs_upserted": 2,
        "bucket_b_issues_scanned": 0,
        "bucket_b_worklogs_upserted": 3,
        "bucket_b_out_of_scope_created": 1,
    }
