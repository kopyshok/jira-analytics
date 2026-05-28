"""Тесты UsageService — запись событий и валидация."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import User, UsageDaily, UsageEvent, UsageEventType, UserRole
from app.services.usage_service import UsageService


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


def _seed_raw(db_session, user, target, *, kind, path, action_type=None):
    db_session.add(UsageEvent(
        user_id=user.id, event_type=kind, path=path,
        action_type=action_type, at=target,
    ))


def test_aggregate_day_groups_views_seconds_actions(db_session, user):
    svc = UsageService(db_session)
    target = datetime(2026, 5, 27, 10, 0, 0)
    _seed_raw(db_session, user, target, kind=UsageEventType.page_view, path="/dashboard")
    _seed_raw(db_session, user, target, kind=UsageEventType.heartbeat, path="/dashboard")
    _seed_raw(db_session, user, target, kind=UsageEventType.heartbeat, path="/dashboard")
    _seed_raw(db_session, user, target, kind=UsageEventType.action,
              path="/sync", action_type="sync_started")
    db_session.commit()

    svc.aggregate_day(date(2026, 5, 27))
    rows = db_session.query(UsageDaily).all()
    assert len(rows) == 2
    dash = next(r for r in rows if r.path == "/dashboard")
    assert dash.views == 1
    assert dash.seconds == 60
    sync = next(r for r in rows if r.path == "/sync")
    assert json.loads(sync.actions_json) == {"sync_started": 1}


def test_aggregate_day_idempotent(db_session, user):
    svc = UsageService(db_session)
    target = datetime(2026, 5, 27, 10, 0, 0)
    _seed_raw(db_session, user, target, kind=UsageEventType.page_view, path="/dashboard")
    db_session.commit()

    svc.aggregate_day(date(2026, 5, 27))
    svc.aggregate_day(date(2026, 5, 27))
    rows = db_session.query(UsageDaily).all()
    assert len(rows) == 1
    assert rows[0].views == 1


def test_cleanup_old_events_deletes_past_retention(db_session, user):
    svc = UsageService(db_session)
    old = datetime.utcnow() - timedelta(days=100)
    db_session.add(UsageEvent(
        user_id=user.id, event_type=UsageEventType.page_view,
        path="/dashboard", at=old,
    ))
    recent = datetime.utcnow() - timedelta(days=30)
    db_session.add(UsageEvent(
        user_id=user.id, event_type=UsageEventType.page_view,
        path="/dashboard", at=recent,
    ))
    db_session.commit()

    deleted = svc.cleanup_old_events(retention_days=90)
    assert deleted == 1
    assert db_session.query(UsageEvent).count() == 1


def _seed_daily(db_session, user, day, path, views=0, seconds=0, actions=None):
    db_session.add(UsageDaily(
        date=day, user_id=user.id, path=path,
        views=views, seconds=seconds,
        actions_json=json.dumps(actions or {}),
    ))
    db_session.commit()


def test_query_overview_counts_dau_wau_mau(db_session, user):
    today = date.today()
    _seed_daily(db_session, user, today, "/dashboard", views=1, seconds=3600)
    svc = UsageService(db_session)
    out = svc.query_overview()
    assert out["dau"] >= 1
    assert out["wau"] >= 1
    assert out["mau"] >= 1
    assert out["hours_30d"] >= 1.0


def test_query_pages_aggregates_by_path(db_session, user):
    today = date.today()
    _seed_daily(db_session, user, today, "/dashboard", views=3, seconds=1800)
    svc = UsageService(db_session)
    rows = svc.query_pages(days=30)
    by_path = {r["path"]: r for r in rows}
    assert by_path["/dashboard"]["views"] == 3
    assert by_path["/dashboard"]["unique_users"] == 1
    assert by_path["/dashboard"]["hours"] == 0.5
