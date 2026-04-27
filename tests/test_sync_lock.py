"""Tests for SyncLock advisory lock."""

from datetime import datetime, timedelta

import pytest

from app.services.sync_lock import SyncLock


def test_acquire_then_release(db_session):
    lock = SyncLock(db_session)
    assert lock.acquire("run-1") is True
    assert lock.current_run_id() == "run-1"
    lock.release()
    assert lock.current_run_id() is None


def test_acquire_fails_if_held(db_session):
    lock = SyncLock(db_session)
    assert lock.acquire("run-1") is True
    assert lock.acquire("run-2") is False
    assert lock.current_run_id() == "run-1"


def test_stale_lock_older_than_ttl_treated_as_free(db_session):
    lock = SyncLock(db_session, stale_after_minutes=60)
    lock.acquire("run-old")
    # Перемотаем started_at в прошлое
    lock._set_started_at(datetime.utcnow() - timedelta(minutes=120))
    assert lock.is_stale() is True
    assert lock.acquire("run-new") is True
    assert lock.current_run_id() == "run-new"
