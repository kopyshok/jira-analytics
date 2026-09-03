"""Правка реестра команд и групп доступна только администратору."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.user import User, UserRole


def _login(db, role: UserRole) -> tuple[TestClient, dict]:
    email = f"registry_{role.value}_{uuid.uuid4().hex[:8]}@example.com"
    db.add(
        User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password("pass123"),
            display_name="Registry Tester",
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
def test_manager_cannot_change_registry(testclient_db_session):
    client, headers = _login(testclient_db_session, UserRole.manager)
    try:
        assert client.get("/api/v1/teams/registry", headers=headers).status_code == 200

        assert client.patch(
            "/api/v1/teams/registry/Команда А",
            json={"has_subgroups": True},
            headers=headers,
        ).status_code == 403
        assert client.post(
            "/api/v1/teams/registry/Команда А/subgroups",
            json={"name": "Группа 1"},
            headers=headers,
        ).status_code == 403
        assert client.patch(
            "/api/v1/teams/subgroups/whatever", json={"name": "X"}, headers=headers
        ).status_code == 403
        assert client.delete(
            "/api/v1/teams/subgroups/whatever", headers=headers
        ).status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.no_auth_bypass
def test_admin_can_change_registry(testclient_db_session):
    client, headers = _login(testclient_db_session, UserRole.admin)
    try:
        resp = client.patch(
            "/api/v1/teams/registry/Команда А",
            json={"has_subgroups": True},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["has_subgroups"] is True

        created = client.post(
            "/api/v1/teams/registry/Команда А/subgroups",
            json={"name": "Группа 1"},
            headers=headers,
        )
        assert created.status_code == 201, created.text
    finally:
        app.dependency_overrides.clear()
