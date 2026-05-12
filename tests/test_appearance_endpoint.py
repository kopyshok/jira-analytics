"""Tests for GET/PUT /me/appearance endpoint."""

import uuid
import pytest
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
        display_name="Appearance Tester",
        role=UserRole.manager,
    )
    db.add(u)
    db.commit()
    return u


def _make_authed_client(db) -> tuple[TestClient, dict]:
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"email": "appear_test@example.com", "password": "pass123"})
    assert r.status_code == 200, f"Login failed: {r.text}"
    token = r.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


@pytest.mark.no_auth_bypass
def test_get_appearance_returns_defaults(testclient_db_session):
    """GET без сохранённых настроек возвращает дефолты."""
    _seed_user(testclient_db_session, "appear_test@example.com")
    client, headers = _make_authed_client(testclient_db_session)
    try:
        r = client.get("/api/v1/users/me/appearance", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["phase_colors"]["analyst"] == "#00c9c8"
        assert data["phase_colors"]["dev"] == "#2a7fbf"
        assert data["phase_colors"]["qa"] == "#e8864a"
        assert data["phase_colors"]["opo"] == "#52d364"
        assert data["initiative_bracket_color"] == "#b8c9e0"
        assert data["initiative_fill_intensity"] == "medium"
        assert data["animation_speed_seconds"] == 4.0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.no_auth_bypass
def test_put_appearance_persisted_on_get(testclient_db_session):
    """PUT валидной палитры сохраняется, повторный GET возвращает новые значения."""
    _seed_user(testclient_db_session, "appear_test@example.com")
    client, headers = _make_authed_client(testclient_db_session)
    try:
        payload = {
            "phase_colors": {
                "analyst": "#ff0000",
                "dev": "#00ff00",
                "qa": "#0000ff",
                "opo": "#ffff00",
            },
            "initiative_bracket_color": "#aabbcc",
            "initiative_fill_intensity": "dense",
            "animation_speed_seconds": 8.0,
        }
        r = client.put("/api/v1/users/me/appearance", json=payload, headers=headers)
        assert r.status_code == 200
        saved = r.json()
        assert saved["phase_colors"]["analyst"] == "#ff0000"
        assert saved["initiative_fill_intensity"] == "dense"
        assert saved["animation_speed_seconds"] == 8.0

        # GET должен вернуть сохранённое
        r2 = client.get("/api/v1/users/me/appearance", headers=headers)
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["phase_colors"]["analyst"] == "#ff0000"
        assert data2["initiative_bracket_color"] == "#aabbcc"
        assert data2["initiative_fill_intensity"] == "dense"
        assert data2["animation_speed_seconds"] == 8.0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.no_auth_bypass
def test_put_invalid_hex_color_returns_422(testclient_db_session):
    """PUT с невалидным цветом возвращает 422."""
    _seed_user(testclient_db_session, "appear_test@example.com")
    client, headers = _make_authed_client(testclient_db_session)
    try:
        payload = {
            "phase_colors": {
                "analyst": "not-hex",
                "dev": "#2a7fbf",
                "qa": "#e8864a",
                "opo": "#52d364",
            },
            "initiative_bracket_color": "#b8c9e0",
            "initiative_fill_intensity": "medium",
            "animation_speed_seconds": 4.0,
        }
        r = client.put("/api/v1/users/me/appearance", json=payload, headers=headers)
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.no_auth_bypass
def test_put_animation_speed_out_of_range_returns_422(testclient_db_session):
    """PUT со скоростью анимации вне диапазона [0.5, 20] возвращает 422."""
    _seed_user(testclient_db_session, "appear_test@example.com")
    client, headers = _make_authed_client(testclient_db_session)
    try:
        payload = {
            "phase_colors": {
                "analyst": "#00c9c8",
                "dev": "#2a7fbf",
                "qa": "#e8864a",
                "opo": "#52d364",
            },
            "initiative_bracket_color": "#b8c9e0",
            "initiative_fill_intensity": "medium",
            "animation_speed_seconds": 100.0,
        }
        r = client.put("/api/v1/users/me/appearance", json=payload, headers=headers)
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()
