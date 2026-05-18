"""Endpoint tests for GET/PUT /me/analytics-layout."""
import uuid

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.user import User, UserRole


def _seed_user(db, email: str) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password("pass123"),
        display_name="Layout Tester",
        role=UserRole.manager,
    )
    db.add(u)
    db.commit()
    return u


def _make_authed_client(db) -> tuple[TestClient, dict]:
    """Returns (client, auth_headers)."""
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"email": "layout_test@example.com", "password": "pass123"})
    token = r.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_get_default_analytics_layout(testclient_db_session):
    _seed_user(testclient_db_session, "layout_test@example.com")
    client, headers = _make_authed_client(testclient_db_session)
    try:
        response = client.get("/api/v1/users/me/analytics-layout", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"layout": {}}
    finally:
        app.dependency_overrides.clear()


def test_put_then_get_layout(testclient_db_session):
    _seed_user(testclient_db_session, "layout_test@example.com")
    client, headers = _make_authed_client(testclient_db_session)
    try:
        payload = {
            "layout": {
                "group_order": ["employee", "category", "issue"],
                "hidden_levels": ["team", "role", "work_type"],
                "active_preset": "people",
            }
        }
        put = client.put("/api/v1/users/me/analytics-layout", json=payload, headers=headers)
        assert put.status_code == 200
        got = client.get("/api/v1/users/me/analytics-layout", headers=headers)
        assert got.json()["layout"] == payload["layout"]
    finally:
        app.dependency_overrides.clear()
