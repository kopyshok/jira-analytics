"""Tests for POST /sync/issues/reload/stream."""

import json
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import AppSetting, Issue, Project


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
    """Stand-in for ``async with JiraClient.from_db(db)`` — сам SyncService
    в тестах замокан, поэтому реальный клиент не нужен."""
    yield object()


def _parse_sse(raw: str) -> list[dict]:
    events: list[dict] = []
    for block in raw.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data:"):
                events.append(json.loads(line.removeprefix("data:").strip()))
    return events


def test_reload_issues_stream_calls_service_with_since_and_emits_events(client, db_session):
    # Pin the session's connection to the test thread (см. test_sync_reload_endpoint.py).
    db_session.query(AppSetting).first()

    project = Project(jira_project_id="p1", key="PRJ", name="Project")
    issue = Issue(
        jira_issue_id="1", key="PRJ-1", summary="s",
        issue_type="Task", status="Open", project=project,
    )
    db_session.add_all([project, issue])
    db_session.commit()
    issue_id = issue.id

    captured_kwargs: dict = {}

    async def fake_sync_issues(self, project_keys=None, incremental=True, since_override=None, on_progress=None):
        captured_kwargs["since_override"] = since_override
        self.stats.issues_synced = 1
        self.stats.issues_created = 0
        self.stats.touched_issue_keys.add("PRJ-1")
        if on_progress is not None:
            await on_progress(self.stats, "PRJ-1")
        return 1

    with patch(
        "app.api.endpoints.sync.JiraClient.from_db",
        return_value=_fake_jira_ctx(),
    ), patch(
        "app.services.sync_service.SyncService.sync_issues",
        new=fake_sync_issues,
    ), patch(
        "app.services.mapping_service.MappingService.recalculate_for_issues",
        return_value=1,
    ) as mock_recalc:
        with client.stream(
            "POST",
            "/api/v1/sync/issues/reload/stream",
            json={"since": "2026-01-01"},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = resp.read().decode("utf-8")

    from datetime import date
    assert captured_kwargs["since_override"] == date(2026, 1, 1)

    events = _parse_sse(body)
    types = [e["type"] for e in events]
    assert types[0] == "progress"
    assert types[-1] == "done"

    done = events[-1]
    assert done == {
        "type": "done",
        "issues_synced": 1,
        "issues_created": 0,
        "mapping_affected": 1,
    }

    # Пересчёт категорий вызван только для затронутых задач, как в стадии
    # mapping обычного pipeline — не полный recalculate_all.
    mock_recalc.assert_called_once_with([issue_id])

    setting = (
        db_session.query(AppSetting)
        .filter(AppSetting.key == "issues_reload_since_date")
        .one_or_none()
    )
    assert setting is not None
    assert setting.value == "2026-01-01"


def test_reload_issues_stream_rejects_invalid_date(client):
    resp = client.post(
        "/api/v1/sync/issues/reload/stream", json={"since": "not-a-date"}
    )
    assert resp.status_code == 422


def test_reload_issues_stream_no_touched_keys_skips_mapping(client, db_session):
    db_session.query(AppSetting).first()

    async def fake_sync_issues(self, project_keys=None, incremental=True, since_override=None, on_progress=None):
        return 0

    with patch(
        "app.api.endpoints.sync.JiraClient.from_db",
        return_value=_fake_jira_ctx(),
    ), patch(
        "app.services.sync_service.SyncService.sync_issues",
        new=fake_sync_issues,
    ), patch(
        "app.services.mapping_service.MappingService.recalculate_for_issues",
    ) as mock_recalc:
        with client.stream(
            "POST",
            "/api/v1/sync/issues/reload/stream",
            json={"since": "2026-02-01"},
        ) as resp:
            body = resp.read().decode("utf-8")

    mock_recalc.assert_not_called()
    events = _parse_sse(body)
    assert events[-1]["mapping_affected"] == 0
