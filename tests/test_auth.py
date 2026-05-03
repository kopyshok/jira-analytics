import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app
from app.core.security import hash_password
from app.models.user import User, UserRole

pytestmark = pytest.mark.no_auth_bypass


def _make_client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _teardown():
    app.dependency_overrides.clear()


def _seed(db: Session, email: str, role: UserRole = UserRole.manager,
          team: str | None = "Team A", active: bool = True) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password("password123"),
        display_name="Test",
        role=role,
        default_team=team,
        is_active=active,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_login_success(testclient_db_session):
    _seed(testclient_db_session, "ok@example.com")
    client = _make_client(testclient_db_session)
    try:
        r = client.post("/api/v1/auth/login", json={"email": "ok@example.com", "password": "password123"})
        assert r.status_code == 200
        assert "access_token" in r.json()
        assert r.json()["token_type"] == "bearer"
    finally:
        _teardown()


def test_login_wrong_password(testclient_db_session):
    _seed(testclient_db_session, "wp@example.com")
    client = _make_client(testclient_db_session)
    try:
        r = client.post("/api/v1/auth/login", json={"email": "wp@example.com", "password": "wrong"})
        assert r.status_code == 401
    finally:
        _teardown()


def test_login_unknown_email(testclient_db_session):
    client = _make_client(testclient_db_session)
    try:
        r = client.post("/api/v1/auth/login", json={"email": "nope@example.com", "password": "x"})
        assert r.status_code == 401
    finally:
        _teardown()


def test_login_inactive_user(testclient_db_session):
    _seed(testclient_db_session, "inactive@example.com", active=False)
    client = _make_client(testclient_db_session)
    try:
        r = client.post("/api/v1/auth/login", json={"email": "inactive@example.com", "password": "password123"})
        assert r.status_code == 403
    finally:
        _teardown()


def test_me_returns_profile(testclient_db_session):
    _seed(testclient_db_session, "me@example.com", team="Team B")
    client = _make_client(testclient_db_session)
    try:
        login_r = client.post("/api/v1/auth/login", json={"email": "me@example.com", "password": "password123"})
        token = login_r.json()["access_token"]
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == "me@example.com"
        assert r.json()["default_team"] == "Team B"
    finally:
        _teardown()


def test_me_invalid_token(testclient_db_session):
    client = _make_client(testclient_db_session)
    try:
        r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad.token.here"})
        assert r.status_code == 401
    finally:
        _teardown()
