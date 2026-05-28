"""Тесты UsageService — запись событий и валидация."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import User, UsageEvent, UsageEventType, UserRole
from app.services.usage_service import UsageService, ALLOWED_PATHS


@pytest.fixture
def user(db_session):
    u = User(
        email="u@test", password_hash="x", display_name="U",
        role=UserRole.manager,
    )
    db_session.add(u)
    db_session.commit()
    return u


def test_record_events_accepts_known_path(db_session, user):
    svc = UsageService(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    res = svc.record_events(user_id=user.id, events=[
        {"event_type": "page_view", "path": "/dashboard", "at": now},
    ])
    assert res == {"accepted": 1, "rejected": 0}
    rows = db_session.query(UsageEvent).all()
    assert len(rows) == 1
    assert rows[0].event_type == UsageEventType.page_view


def test_record_events_rejects_unknown_path(db_session, user):
    svc = UsageService(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    res = svc.record_events(user_id=user.id, events=[
        {"event_type": "page_view", "path": "/nonsense", "at": now},
    ])
    assert res == {"accepted": 0, "rejected": 1}
    assert db_session.query(UsageEvent).count() == 0


def test_record_events_rejects_old_timestamp(db_session, user):
    svc = UsageService(db_session)
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
    res = svc.record_events(user_id=user.id, events=[
        {"event_type": "page_view", "path": "/dashboard", "at": old},
    ])
    assert res == {"accepted": 0, "rejected": 1}


def test_record_events_action_requires_action_type(db_session, user):
    svc = UsageService(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    res = svc.record_events(user_id=user.id, events=[
        {"event_type": "action", "path": "/dashboard", "at": now},
    ])
    assert res == {"accepted": 0, "rejected": 1}
