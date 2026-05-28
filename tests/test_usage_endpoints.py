"""Тесты client-facing /usage/events."""
import uuid
from datetime import datetime

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user, require_admin
from app.database import get_db
from app.main import app
from app.models.user import User, UserRole


def _seed_user(db: Session, role: UserRole = UserRole.manager) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=f"{uuid.uuid4()}@test",
        password_hash="x",
        display_name="Tester",
        role=role,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _set_user(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user

    def _require_admin_impl() -> User:
        if user.role != UserRole.admin:
            raise HTTPException(status_code=403, detail="Только для администратора")
        return user

    app.dependency_overrides[require_admin] = _require_admin_impl


def _set_no_user() -> None:
    """Симулируем отсутствие аутентификации — 401."""
    def _raise() -> User:
        raise HTTPException(status_code=401, detail="Не авторизован")

    app.dependency_overrides[get_current_user] = _raise
    app.dependency_overrides[require_admin] = _raise


def _teardown() -> None:
    app.dependency_overrides.clear()


def test_post_events_inserts(testclient_db_session: Session) -> None:
    user = _seed_user(testclient_db_session)
    client = _make_client(testclient_db_session)
    try:
        _set_user(user)
        now = datetime.utcnow().isoformat()
        r = client.post("/api/v1/usage/events", json={"events": [
            {"event_type": "page_view", "path": "/dashboard", "at": now},
            {"event_type": "heartbeat", "path": "/dashboard", "at": now},
        ]})
        assert r.status_code == 200, r.text
        assert r.json() == {"accepted": 2, "rejected": 0}
    finally:
        _teardown()


def test_post_events_ignores_garbage(testclient_db_session: Session) -> None:
    user = _seed_user(testclient_db_session)
    client = _make_client(testclient_db_session)
    try:
        _set_user(user)
        now = datetime.utcnow().isoformat()
        r = client.post("/api/v1/usage/events", json={"events": [
            {"event_type": "page_view", "path": "/dashboard", "at": now},
            {"event_type": "page_view", "path": "/garbage", "at": now},
        ]})
        assert r.status_code == 200
        assert r.json() == {"accepted": 1, "rejected": 1}
    finally:
        _teardown()


def test_post_events_requires_auth(testclient_db_session: Session) -> None:
    client = _make_client(testclient_db_session)
    try:
        _set_no_user()
        now = datetime.utcnow().isoformat()
        r = client.post("/api/v1/usage/events", json={"events": [
            {"event_type": "page_view", "path": "/dashboard", "at": now},
        ]})
        assert r.status_code in (401, 403)
    finally:
        _teardown()
