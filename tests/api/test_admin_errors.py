"""Список последних ошибок сервера: доступ и наполнение."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core import error_log
from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.user import User, UserRole


def _login(db, role: UserRole) -> tuple[TestClient, dict]:
    email = f"errlog_{role.value}_{uuid.uuid4().hex[:8]}@example.com"
    db.add(
        User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password("pass123"),
            display_name="Errlog Tester",
            role=role,
        )
    )
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "pass123"})
    assert resp.status_code == 200, resp.text
    return client, {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.no_auth_bypass
def test_only_admin_sees_errors(testclient_db_session):
    client, headers = _login(testclient_db_session, UserRole.manager)
    try:
        assert client.get("/api/v1/admin/errors", headers=headers).status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)

    client, headers = _login(testclient_db_session, UserRole.admin)
    try:
        assert client.get("/api/v1/admin/errors", headers=headers).status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_unhandled_error_lands_in_list(testclient_db_session):
    """Падение запроса попадает в буфер и отдаётся с номером."""
    error_log.clear()

    @app.get("/api/v1/__selftest_boom")
    def _boom() -> None:
        raise RuntimeError("тестовый сбой")

    app.dependency_overrides[get_db] = lambda: testclient_db_session
    client = TestClient(app, raise_server_exceptions=False)
    try:
        resp = client.get("/api/v1/__selftest_boom")
        assert resp.status_code == 500
        error_id = resp.json()["error_id"]

        item = client.get("/api/v1/admin/errors").json()["items"][0]
        assert item["id"] == error_id
        assert item["path"] == "/api/v1/__selftest_boom"
        assert item["error_type"] == "RuntimeError"
        assert "тестовый сбой" in item["traceback"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.router.routes = [
            r for r in app.router.routes
            if getattr(r, "path", None) != "/api/v1/__selftest_boom"
        ]
        error_log.clear()
