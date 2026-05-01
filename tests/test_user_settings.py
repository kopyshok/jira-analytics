"""Model-level tests for User.selected_period and User.analytics_columns."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.user import User, UserRole


@pytest.fixture
def user(db_session):
    u = User(
        email="test_settings@example.com",
        password_hash="hashed",
        display_name="Test User",
        role=UserRole.manager,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def test_selected_period_default_and_roundtrip(db_session, user):
    # Defaults
    assert user.selected_period == {}
    assert user.analytics_columns == []

    # Set and commit
    user.selected_period = {"year": 2026, "quarter": 2, "month": 4}
    user.analytics_columns = ["employee", "hours", "category"]
    db_session.commit()
    db_session.refresh(user)

    # Verify persistence
    assert user.selected_period == {"year": 2026, "quarter": 2, "month": 4}
    assert user.analytics_columns == ["employee", "hours", "category"]


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

def _seed_user(db, email: str) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password("pass123"),
        display_name="Endpoint Tester",
        role=UserRole.manager,
    )
    db.add(u)
    db.commit()
    return u


def _make_authed_client(db) -> tuple[TestClient, dict]:
    """Returns (client, auth_headers)."""
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"email": "ep_test@example.com", "password": "pass123"})
    token = r.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_get_set_my_period(testclient_db_session):
    _seed_user(testclient_db_session, "ep_test@example.com")
    client, headers = _make_authed_client(testclient_db_session)
    try:
        resp = client.get("/api/v1/users/me/period", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {}

        resp = client.put(
            "/api/v1/users/me/period",
            json={"year": 2026, "quarter": 2, "month": 4},
            headers=headers,
        )
        assert resp.status_code == 200

        resp = client.get("/api/v1/users/me/period", headers=headers)
        assert resp.json() == {"year": 2026, "quarter": 2, "month": 4}
    finally:
        app.dependency_overrides.clear()


def test_get_set_my_analytics_columns(testclient_db_session):
    _seed_user(testclient_db_session, "ep_test@example.com")
    client, headers = _make_authed_client(testclient_db_session)
    try:
        resp = client.get("/api/v1/users/me/analytics-columns", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"columns": []}

        resp = client.put(
            "/api/v1/users/me/analytics-columns",
            json={"columns": ["employee", "hours", "category"]},
            headers=headers,
        )
        assert resp.status_code == 200

        resp = client.get("/api/v1/users/me/analytics-columns", headers=headers)
        assert resp.json() == {"columns": ["employee", "hours", "category"]}
    finally:
        app.dependency_overrides.clear()


def test_period_partial_update(testclient_db_session):
    """PUT with only year+quarter should not write null for month."""
    _seed_user(testclient_db_session, "ep_test@example.com")
    client, headers = _make_authed_client(testclient_db_session)
    try:
        client.put(
            "/api/v1/users/me/period",
            json={"year": 2026, "quarter": 3},
            headers=headers,
        )
        resp = client.get("/api/v1/users/me/period", headers=headers)
        data = resp.json()
        assert data == {"year": 2026, "quarter": 3}
        assert "month" not in data
    finally:
        app.dependency_overrides.clear()


def test_period_requires_auth(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    client = TestClient(app)
    try:
        resp = client.get("/api/v1/users/me/period")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
