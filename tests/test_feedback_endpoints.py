"""Endpoint-уровень для /feedback."""
import uuid

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user, require_admin
from app.database import get_db
from app.main import app
from app.models.user import User, UserRole


def _seed_user(db: Session, *, email: str, role: UserRole, display_name: str) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash="x",
        display_name=display_name,
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
    """Replace conftest's auth stubs for the duration of one request."""
    app.dependency_overrides[get_current_user] = lambda: user

    def _require_admin_impl() -> User:
        if user.role != UserRole.admin:
            raise HTTPException(status_code=403, detail="Только для администратора")
        return user

    app.dependency_overrides[require_admin] = _require_admin_impl


def _teardown() -> None:
    app.dependency_overrides.clear()


# --- Task A8: user endpoints ---


def test_create_bug_as_manager(testclient_db_session: Session) -> None:
    manager = _seed_user(
        testclient_db_session, email="m@example.com", role=UserRole.manager, display_name="Mgr"
    )
    client = _make_client(testclient_db_session)
    try:
        _set_user(manager)
        r = client.post(
            "/api/v1/feedback/bugs",
            json={"title": "Crash", "body": "freezes", "page_url": "/x"},
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["kind"] == "bug"
        assert data["author"]["id"] == manager.id
    finally:
        _teardown()


def test_create_idea_as_manager(testclient_db_session: Session) -> None:
    manager = _seed_user(
        testclient_db_session, email="m@example.com", role=UserRole.manager, display_name="Mgr"
    )
    client = _make_client(testclient_db_session)
    try:
        _set_user(manager)
        r = client.post(
            "/api/v1/feedback/ideas", json={"title": "Idea", "body": "Add CSV"}
        )
        assert r.status_code == 201
        assert r.json()["kind"] == "idea"
    finally:
        _teardown()


def test_list_my_returns_only_my(testclient_db_session: Session) -> None:
    manager = _seed_user(
        testclient_db_session, email="m@example.com", role=UserRole.manager, display_name="Mgr"
    )
    admin = _seed_user(
        testclient_db_session, email="a@example.com", role=UserRole.admin, display_name="Adm"
    )
    client = _make_client(testclient_db_session)
    try:
        _set_user(manager)
        client.post("/api/v1/feedback/bugs", json={"title": "Mine", "body": "x"})
        _set_user(admin)
        client.post("/api/v1/feedback/bugs", json={"title": "AdminBug", "body": "y"})
        _set_user(manager)
        r = client.get("/api/v1/feedback/my")
        assert r.status_code == 200
        titles = [it["title"] for it in r.json()]
        assert titles == ["Mine"]
    finally:
        _teardown()


def test_list_ideas_public_visible_to_all(testclient_db_session: Session) -> None:
    manager = _seed_user(
        testclient_db_session, email="m@example.com", role=UserRole.manager, display_name="Mgr"
    )
    admin = _seed_user(
        testclient_db_session, email="a@example.com", role=UserRole.admin, display_name="Adm"
    )
    client = _make_client(testclient_db_session)
    try:
        _set_user(admin)
        client.post("/api/v1/feedback/ideas", json={"title": "Admin idea", "body": "x"})
        _set_user(manager)
        r = client.get("/api/v1/feedback/ideas?scope=all")
        assert r.status_code == 200
        titles = [it["title"] for it in r.json()]
        assert "Admin idea" in titles
    finally:
        _teardown()
