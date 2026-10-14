"""Пока переезд на новую Jira не завершён, каждый пишущий путь синка отказывает."""
import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.jobs.backfill_issue_author import FLAG_KEY, backfill_issue_author_once
from app.main import app
from app.models.app_setting import AppSetting
from app.repositories.sync_run import SyncRunRepository
from app.repositories.sync_schedule import SyncScheduleRepository
from app.services.jira_migration.state import (
    STATE_DONE,
    STATE_PENDING,
    SYNC_BLOCKED_MESSAGE,
    set_migration_state,
)
from app.services.scheduler import scheduled_pipeline_runner
from app.services.sync_lock import SyncLock

WRITING_ENDPOINTS = [
    ("/api/v1/sync/pipeline", {"mode": "quick"}),
    ("/api/v1/sync/team/refresh", {"team": "Команда"}),
    ("/api/v1/sync/projects", None),
    ("/api/v1/sync/issues", None),
    ("/api/v1/sync/issues/refresh", {"jira_keys": ["OS-1"]}),
    ("/api/v1/sync/issues/reload/stream", {"since": "2026-01-01"}),
    ("/api/v1/sync/teams", {"teams": ["Команда"]}),
    ("/api/v1/sync/worklogs", None),
    ("/api/v1/sync/worklogs/reload", {"since": "2026-01-01"}),
    ("/api/v1/sync/worklogs/reload/stream", {"since": "2026-01-01"}),
    ("/api/v1/sync/worklogs/update/stream", {"since": "2026-01-01"}),
    ("/api/v1/sync/comments", None),
    ("/api/v1/sync/full", None),
    ("/api/v1/team-desk/refresh-issues", {"keys": ["OS-1"]}),
    ("/api/v1/backlog/refresh-from-jira", None),
    ("/api/v1/backlog/refresh-from-jira/stream", None),
]


@pytest.fixture
def pending_client(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    with patch(
        "app.connectors.jira_client.JiraClient.from_db",
        side_effect=AssertionError("Jira не должна вызываться"),
    ):
        yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("path, body", WRITING_ENDPOINTS)
def test_writing_endpoint_refuses_while_pending(pending_client, db_session, path, body):
    if body is None:
        resp = pending_client.post(path)
    else:
        resp = pending_client.post(path, json=body)
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == SYNC_BLOCKED_MESSAGE
    # Отказ раньше, чем заведён прогон и взята блокировка синка.
    assert SyncRunRepository(db_session).list_latest(limit=5) == []
    assert SyncLock(db_session).current_run_id() is None


def test_run_schedule_now_refuses_while_pending(pending_client, db_session):
    schedule = SyncScheduleRepository(db_session).create(
        name="Ночной", cron_expr="0 3 * * *", mode="quick",
    )
    schedule_id = schedule.id
    resp = pending_client.post(f"/api/v1/sync/schedule/{schedule_id}/run-now")
    assert resp.status_code == 409
    assert resp.json()["detail"] == SYNC_BLOCKED_MESSAGE
    assert SyncRunRepository(db_session).list_latest(limit=5) == []
    assert SyncLock(db_session).current_run_id() is None


def test_refresh_allowed_when_done(db_session):
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        resp = TestClient(app).post("/api/v1/sync/issues/refresh", json={"jira_keys": []})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 200
    assert resp.json()["status"] == "noop"


async def test_scheduler_skips_while_pending(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    with patch("app.services.scheduler._get_db_session", return_value=db_session), \
            patch("app.services.scheduler.JiraClient") as jira_cls:
        await scheduled_pipeline_runner(schedule_id="sched-x", mode="quick", team=None)
    jira_cls.from_db.assert_not_called()
    assert SyncRunRepository(db_session).list_latest(limit=5) == []


def test_backfill_skips_while_pending(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()

    class _NoJira:
        async def __aenter__(self):
            raise AssertionError("Jira не должна вызываться")

        async def __aexit__(self, *exc):
            return False

    changed = asyncio.run(
        backfill_issue_author_once(client=_NoJira(), _session_factory=lambda: db_session)
    )
    assert changed == 0
    assert db_session.query(AppSetting).filter_by(key=FLAG_KEY).first() is None


def test_ui_config_exposes_state(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        resp = TestClient(app).get("/api/v1/ui-config/jira-migration-state")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 200
    assert resp.json() == {"state": "pending", "sync_blocked": True}


def test_ui_config_exposes_done_state(db_session):
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        resp = TestClient(app).get("/api/v1/ui-config/jira-migration-state")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 200
    assert resp.json() == {"state": "done", "sync_blocked": False}


def test_stale_field_script_refuses_apply_while_pending(db_session, monkeypatch, capsys):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    path = Path(__file__).resolve().parents[2] / "scripts" / "clear_stale_developer_field.py"
    spec = importlib.util.spec_from_file_location("clear_stale_developer_field", path)
    script = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(sys, "path", list(sys.path))  # скрипт дописывает sys.path
    spec.loader.exec_module(script)
    monkeypatch.setattr(script, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(sys, "argv", ["clear_stale_developer_field.py", "--apply"])
    with patch.object(
        script.JiraClient, "from_db",
        side_effect=AssertionError("Jira не должна вызываться"),
    ):
        code = asyncio.run(script.main())
    assert code == 1
    assert SYNC_BLOCKED_MESSAGE in capsys.readouterr().err
