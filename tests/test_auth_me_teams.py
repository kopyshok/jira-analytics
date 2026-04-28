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


def _seed(db: Session, email: str, selected_teams: list[str] | None = None) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password("password123"),
        display_name="Test",
        role=UserRole.manager,
        default_team="Team A",
        is_active=True,
    )
    if selected_teams is not None:
        u.selected_teams = selected_teams
    db.add(u)
    db.commit()
    return u


def _login(client: TestClient, email: str) -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return r.json()["access_token"]


def test_put_me_teams_updates_selected_teams(testclient_db_session):
    _seed(testclient_db_session, "teams1@example.com")
    client = _make_client(testclient_db_session)
    try:
        token = _login(client, "teams1@example.com")
        r = client.put(
            "/api/v1/auth/me/teams",
            json={"teams": ["T1", "T2"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["selected_teams"] == ["T1", "T2"]
    finally:
        _teardown()


def test_put_me_teams_replaces_wholesale(testclient_db_session):
    _seed(testclient_db_session, "teams2@example.com", selected_teams=["A", "B"])
    client = _make_client(testclient_db_session)
    try:
        token = _login(client, "teams2@example.com")
        r = client.put(
            "/api/v1/auth/me/teams",
            json={"teams": ["C"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["selected_teams"] == ["C"]
    finally:
        _teardown()


def test_put_me_teams_no_auth_returns_401(testclient_db_session):
    client = _make_client(testclient_db_session)
    try:
        r = client.put("/api/v1/auth/me/teams", json={"teams": ["X"]})
        assert r.status_code == 401
    finally:
        _teardown()
