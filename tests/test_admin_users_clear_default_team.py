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


def _seed_with_team(db: Session, email: str, default_team: str) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password("pass"),
        display_name="User A",
        role=UserRole.manager,
        default_team=default_team,
        is_active=True,
    )
    db.add(u)
    db.commit()
    return u


def test_clear_default_team_with_explicit_null(testclient_db_session):
    """PUT with {"default_team": null} must clear an existing non-null default_team."""
    u = _seed_with_team(testclient_db_session, "clear@x.com", "Team Alpha")
    client = _make_client(testclient_db_session)
    try:
        r = client.put(f"/api/v1/admin/users/{u.id}", json={"default_team": None})
        assert r.status_code == 200
        assert r.json()["default_team"] is None
    finally:
        _teardown()


def test_omit_default_team_does_not_clear(testclient_db_session):
    """PUT with only display_name (default_team omitted) must NOT clear existing default_team."""
    u = _seed_with_team(testclient_db_session, "keep@x.com", "Team Beta")
    client = _make_client(testclient_db_session)
    try:
        r = client.put(f"/api/v1/admin/users/{u.id}", json={"display_name": "B2"})
        assert r.status_code == 200
        data = r.json()
        assert data["display_name"] == "B2"
        assert data["default_team"] == "Team Beta"
    finally:
        _teardown()
