"""Tests for SyncLock advisory lock."""

from datetime import datetime, timedelta


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


def test_heartbeat_keeps_own_lock_fresh(db_session):
    lock = SyncLock(db_session)
    assert lock.acquire("run-1")
    lock._set_started_at(datetime.utcnow() - timedelta(minutes=90))
    assert lock.is_stale()
    assert lock.heartbeat("run-1") is True
    assert not lock.is_stale()
    assert lock.current_run_id() == "run-1"


def test_heartbeat_ignores_foreign_lock(db_session):
    lock = SyncLock(db_session)
    assert lock.acquire("run-1")
    lock._set_started_at(datetime.utcnow() - timedelta(minutes=90))
    assert lock.heartbeat("run-2") is False
    assert lock.is_stale()
    assert lock.current_run_id() == "run-1"


def test_heartbeat_without_lock_does_nothing(db_session):
    lock = SyncLock(db_session)
    assert lock.heartbeat("run-1") is False
    assert lock.current_run_id() is None


def test_acquire_loses_race_when_lock_changed_after_read(db_session):
    """Двое прочли зависшую блокировку; первый взял её — второй получает отказ."""
    lock = SyncLock(db_session)
    lock.acquire("run-1")
    lock._set_started_at(datetime.utcnow() - timedelta(minutes=90))
    snapshot = lock._raw()
    assert SyncLock(db_session).acquire("run-2") is True

    late = SyncLock(db_session)
    late._raw = lambda: snapshot  # прочитал до того, как run-2 взял блокировку
    assert late.acquire("run-3") is False
    assert SyncLock(db_session).current_run_id() == "run-2"


def test_acquire_loses_insert_race(db_session):
    """Строки ещё не было при чтении, но другой запуск успел её создать — отказ, без ошибки."""
    assert SyncLock(db_session).acquire("run-1") is True
    late = SyncLock(db_session)
    reads = iter([(False, None)])
    real_raw = late._raw
    late._raw = lambda: next(reads, None) or real_raw()

    assert late.acquire("run-2") is False
    assert SyncLock(db_session).current_run_id() == "run-1"


def test_release_own_keeps_foreign_lock(db_session):
    lock = SyncLock(db_session)
    lock.acquire("run-1")
    lock._set_started_at(datetime.utcnow() - timedelta(minutes=90))
    assert SyncLock(db_session).acquire("run-2") is True

    lock.release("run-1")

    assert lock.current_run_id() == "run-2"
    lock.release("run-2")
    assert lock.current_run_id() is None


def test_acquire_replacing_dead_run_takes_its_fresh_lock(db_session):
    """Запуск заведомо мёртв (сервис перезапустился) — его свежая блокировка не мешает; чужая — мешает."""
    lock = SyncLock(db_session)
    assert lock.acquire("dead-run")
    assert lock.acquire("run-2", replacing="other-run") is False
    assert lock.acquire("run-2", replacing="dead-run") is True
    assert lock.current_run_id() == "run-2"
