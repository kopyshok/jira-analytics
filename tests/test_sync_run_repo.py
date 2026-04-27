"""Tests for SyncRunRepository."""

from datetime import datetime, timedelta

import pytest

from app.models.sync_run import SyncRun
from app.repositories.sync_run import SyncRunRepository


def test_create_and_fetch_latest(db_session):
    repo = SyncRunRepository(db_session)
    run = repo.create(mode="normal", trigger="manual")
    assert run.id is not None
    assert run.status == "running"
    assert run.started_at is not None

    latest = repo.list_latest(limit=10)
    assert latest[0].id == run.id


def test_finalize_sets_status_and_finished_at(db_session):
    repo = SyncRunRepository(db_session)
    run = repo.create(mode="normal", trigger="manual")
    repo.finalize(run.id, status="ok", stages=[{"stage": "projects", "status": "ok"}])

    db_session.refresh(run)
    assert run.status == "ok"
    assert run.finished_at is not None
    assert run.stages_json == [{"stage": "projects", "status": "ok"}]


def test_list_latest_orders_by_started_desc(db_session):
    repo = SyncRunRepository(db_session)
    older = repo.create(mode="quick", trigger="scheduled")
    older.started_at = datetime.utcnow() - timedelta(hours=2)
    db_session.commit()
    newer = repo.create(mode="normal", trigger="manual")

    rows = repo.list_latest(limit=10)
    assert rows[0].id == newer.id
    assert rows[1].id == older.id
