"""Endpoint-уровень для /release-notes (пользовательские)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.main import app
from app.models.release_note import ReleaseNote
from app.models.user import User, UserRole


def _seed_user(db: Session, **kw) -> User:
    defaults = dict(
        id=str(uuid.uuid4()),
        email=f"u-{uuid.uuid4().hex[:6]}@x.com",
        password_hash="x",
        display_name="U",
        role=UserRole.manager,
        is_active=True,
    )
    defaults.update(kw)
    u = User(**defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_note(db: Session, **kw) -> ReleaseNote:
    defaults = dict(
        note_type="improvement", section="general",
        title="T", description="D",
    )
    defaults.update(kw)
    n = ReleaseNote(**defaults)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _client(db: Session, user: User) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _teardown() -> None:
    app.dependency_overrides.clear()


def test_unread_empty_for_fully_caught_up_user(testclient_db_session: Session):
    user = _seed_user(testclient_db_session, last_seen_release_version="v1.0.0")
    _make_note(testclient_db_session, version="v1.0.0")
    try:
        r = _client(testclient_db_session, user).get("/api/v1/release-notes/unread")
        assert r.status_code == 200, r.text
        assert r.json() == {"unread_versions": [], "feeds": []}
    finally:
        _teardown()


def test_unread_returns_versions_after_last_seen(testclient_db_session: Session):
    user = _seed_user(testclient_db_session, last_seen_release_version="v1.0.0")
    _make_note(testclient_db_session, version="v1.0.0")
    _make_note(testclient_db_session, version="v1.1.0")
    _make_note(testclient_db_session, version="v1.1.0", note_type="new")
    try:
        r = _client(testclient_db_session, user).get("/api/v1/release-notes/unread")
        body = r.json()
        assert body["unread_versions"] == ["v1.1.0"]
        assert len(body["feeds"]) == 1
        assert body["feeds"][0]["version"] == "v1.1.0"
        assert len(body["feeds"][0]["notes"]) == 2
    finally:
        _teardown()


def test_unread_skips_hidden(testclient_db_session: Session):
    user = _seed_user(testclient_db_session, last_seen_release_version="v1.0.0")
    _make_note(testclient_db_session, version="v1.1.0", is_hidden=True)
    try:
        r = _client(testclient_db_session, user).get("/api/v1/release-notes/unread")
        assert r.json()["unread_versions"] == []
    finally:
        _teardown()


def test_all_returns_published_only_newest_first(testclient_db_session: Session):
    user = _seed_user(testclient_db_session)
    _make_note(testclient_db_session, version="v1.0.0")
    _make_note(testclient_db_session, version="v1.1.0")
    _make_note(testclient_db_session, version=None)  # draft
    try:
        r = _client(testclient_db_session, user).get("/api/v1/release-notes/all")
        body = r.json()
        versions = [f["version"] for f in body["feeds"]]
        assert versions == ["v1.1.0", "v1.0.0"]
    finally:
        _teardown()


def test_mark_seen_updates_user(testclient_db_session: Session):
    user = _seed_user(testclient_db_session, last_seen_release_version=None)
    _make_note(testclient_db_session, version="v1.1.0")
    try:
        client = _client(testclient_db_session, user)
        r = client.post(
            "/api/v1/release-notes/mark-seen", json={"version": "v1.1.0"}
        )
        assert r.status_code == 204
        testclient_db_session.refresh(user)
        assert user.last_seen_release_version == "v1.1.0"
    finally:
        _teardown()


@pytest.mark.no_auth_bypass
def test_unread_requires_auth():
    """No auth → 401 (verifies router-level auth dep wiring)."""
    client = TestClient(app)
    r = client.get("/api/v1/release-notes/unread")
    assert r.status_code == 401
