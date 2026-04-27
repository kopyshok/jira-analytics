import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app
from app.core.security import hash_password
from app.models.user import User, UserRole


def _make_client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _teardown():
    app.dependency_overrides.clear()


def _seed(db: Session, email: str) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password("pass"),
        display_name="User",
        role=UserRole.manager,
        is_active=True,
    )
    db.add(u)
    db.commit()
    return u


def test_list_users(testclient_db_session):
    _seed(testclient_db_session, "a@x.com")
    _seed(testclient_db_session, "b@x.com")
    client = _make_client(testclient_db_session)
    try:
        r = client.get("/api/v1/admin/users/")
        assert r.status_code == 200
        assert len(r.json()) >= 2
    finally:
        _teardown()


def test_create_user(testclient_db_session):
    client = _make_client(testclient_db_session)
    try:
        r = client.post("/api/v1/admin/users/", json={
            "email": "new@x.com", "password": "secure123",
            "display_name": "New", "role": "manager", "default_team": "Team C",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["email"] == "new@x.com"
        assert data["default_team"] == "Team C"
        assert "password_hash" not in data
    finally:
        _teardown()


def test_create_duplicate_email(testclient_db_session):
    _seed(testclient_db_session, "dup@x.com")
    client = _make_client(testclient_db_session)
    try:
        r = client.post("/api/v1/admin/users/", json={
            "email": "dup@x.com", "password": "pass", "display_name": "D", "role": "manager",
        })
        assert r.status_code == 409
    finally:
        _teardown()


def test_update_user(testclient_db_session):
    u = _seed(testclient_db_session, "upd@x.com")
    client = _make_client(testclient_db_session)
    try:
        r = client.put(f"/api/v1/admin/users/{u.id}", json={"display_name": "Updated"})
        assert r.status_code == 200
        assert r.json()["display_name"] == "Updated"
    finally:
        _teardown()


def test_reset_password(testclient_db_session):
    u = _seed(testclient_db_session, "pwd@x.com")
    client = _make_client(testclient_db_session)
    try:
        r = client.post(f"/api/v1/admin/users/{u.id}/reset-password", json={"new_password": "newpass123"})
        assert r.status_code == 200
        login_r = client.post("/api/v1/auth/login", json={"email": "pwd@x.com", "password": "newpass123"})
        assert login_r.status_code == 200
    finally:
        _teardown()


def test_update_not_found(testclient_db_session):
    client = _make_client(testclient_db_session)
    try:
        r = client.put("/api/v1/admin/users/nonexistent", json={"display_name": "X"})
        assert r.status_code == 404
    finally:
        _teardown()
