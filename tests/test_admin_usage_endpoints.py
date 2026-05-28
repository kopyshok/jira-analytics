"""Admin /admin/usage/* эндпоинты — только админам."""
import uuid
from datetime import date

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user, require_admin
from app.database import get_db
from app.main import app
from app.models import UsageDaily, User, UserRole


def _seed_user(db: Session, role: UserRole) -> User:
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


def _teardown() -> None:
    app.dependency_overrides.clear()


def test_overview_manager_forbidden(testclient_db_session: Session) -> None:
    manager = _seed_user(testclient_db_session, UserRole.manager)
    client = _make_client(testclient_db_session)
    try:
        _set_user(manager)
        r = client.get("/api/v1/admin/usage/overview")
        assert r.status_code == 403
    finally:
        _teardown()


def test_overview_admin_ok(testclient_db_session: Session) -> None:
    admin = _seed_user(testclient_db_session, UserRole.admin)
    testclient_db_session.add(UsageDaily(
        date=date.today(), user_id=admin.id,
        path="/dashboard", views=1, seconds=3600, actions_json="{}",
    ))
    testclient_db_session.commit()
    client = _make_client(testclient_db_session)
    try:
        _set_user(admin)
        r = client.get("/api/v1/admin/usage/overview")
        assert r.status_code == 200, r.text
        body = r.json()
        assert {"dau", "wau", "mau", "hours_30d"} <= set(body.keys())
    finally:
        _teardown()


def test_users_endpoint(testclient_db_session: Session) -> None:
    admin = _seed_user(testclient_db_session, UserRole.admin)
    client = _make_client(testclient_db_session)
    try:
        _set_user(admin)
        r = client.get("/api/v1/admin/usage/users?days=30")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
    finally:
        _teardown()


def test_pages_endpoint(testclient_db_session: Session) -> None:
    admin = _seed_user(testclient_db_session, UserRole.admin)
    client = _make_client(testclient_db_session)
    try:
        _set_user(admin)
        r = client.get("/api/v1/admin/usage/pages?days=30")
        assert r.status_code == 200
    finally:
        _teardown()


def test_matrix_endpoint(testclient_db_session: Session) -> None:
    admin = _seed_user(testclient_db_session, UserRole.admin)
    client = _make_client(testclient_db_session)
    try:
        _set_user(admin)
        r = client.get("/api/v1/admin/usage/matrix?days=30")
        assert r.status_code == 200
        body = r.json()
        assert {"users", "paths", "cells"} <= set(body.keys())
    finally:
        _teardown()


def test_timeline_endpoint(testclient_db_session: Session) -> None:
    admin = _seed_user(testclient_db_session, UserRole.admin)
    client = _make_client(testclient_db_session)
    try:
        _set_user(admin)
        r = client.get("/api/v1/admin/usage/timeline?days=30")
        assert r.status_code == 200
    finally:
        _teardown()


def test_actions_endpoint(testclient_db_session: Session) -> None:
    admin = _seed_user(testclient_db_session, UserRole.admin)
    client = _make_client(testclient_db_session)
    try:
        _set_user(admin)
        r = client.get("/api/v1/admin/usage/actions?days=30")
        assert r.status_code == 200
    finally:
        _teardown()
