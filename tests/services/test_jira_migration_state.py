"""Состояние переезда на Jira DC: пока ``pending``, пишущий синк запрещён."""
import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.models.app_setting import AppSetting
from app.services.jira_migration.state import (
    MIGRATION_STATE_KEY,
    STATE_DONE,
    STATE_PENDING,
    SYNC_BLOCKED_MESSAGE,
    SyncBlockedError,
    ensure_sync_allowed,
    get_migration_state,
    is_sync_blocked,
    set_migration_state,
)
from app.services.sync_service import SyncService


def test_no_row_means_done(db_session):
    assert get_migration_state(db_session) == STATE_DONE
    assert is_sync_blocked(db_session) is False
    ensure_sync_allowed(db_session)


def test_pending_blocks_with_russian_message(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()

    assert is_sync_blocked(db_session) is True
    with pytest.raises(SyncBlockedError) as exc:
        ensure_sync_allowed(db_session)
    assert str(exc.value) == SYNC_BLOCKED_MESSAGE
    assert SYNC_BLOCKED_MESSAGE == "Синхронизация остановлена до завершения переезда на новую Jira"


def test_set_state_does_not_commit(db_session):
    """Применение переезда ставит done в своей транзакции — сеттер не коммитит."""
    set_migration_state(db_session, STATE_PENDING)
    assert is_sync_blocked(db_session) is True
    db_session.rollback()
    assert db_session.query(AppSetting).filter_by(key=MIGRATION_STATE_KEY).first() is None


def test_set_state_updates_existing_row(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()

    rows = db_session.query(AppSetting).filter_by(key=MIGRATION_STATE_KEY).all()
    assert [r.value for r in rows] == [STATE_DONE]


@pytest.mark.parametrize("raw", ["Pending", "pending ", "garbage", ""])
def test_unknown_stored_value_blocks(db_session, raw):
    """Закрыто по умолчанию: всё, кроме ровно ``done``, блокирует синк."""
    db_session.add(AppSetting(key=MIGRATION_STATE_KEY, value=raw))
    db_session.commit()

    assert get_migration_state(db_session) == STATE_PENDING
    with pytest.raises(SyncBlockedError):
        ensure_sync_allowed(db_session)


def test_unknown_state_rejected(db_session):
    with pytest.raises(ValueError):
        set_migration_state(db_session, "half")


def test_sync_service_refuses_while_pending(db_session):
    set_migration_state(db_session, STATE_PENDING)
    db_session.commit()
    with pytest.raises(SyncBlockedError):
        SyncService(db_session, MagicMock())


def test_sync_service_allowed_when_done(db_session):
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()
    SyncService(db_session, MagicMock())


def test_http_handler_returns_409():
    from app.main import app, sync_blocked_handler

    assert app.exception_handlers[SyncBlockedError] is sync_blocked_handler
    response = asyncio.run(sync_blocked_handler(None, SyncBlockedError()))
    assert response.status_code == 409
    assert json.loads(response.body) == {"detail": SYNC_BLOCKED_MESSAGE}
