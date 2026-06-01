"""Endpoint-уровень для /admin/release-notes (CRUD + publish)."""
import uuid

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user, require_admin
from app.database import get_db
from app.main import app
from app.models.release_note import ReleaseNote
from app.models.user import User, UserRole


def _seed_user(db: Session, role: UserRole = UserRole.admin) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=f"u-{uuid.uuid4().hex[:6]}@x.com",
        password_hash="x",
        display_name="U",
        role=role,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _client_admin(db: Session, user: User) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: user
    return TestClient(app)


def _client_as_manager(db: Session, user: User) -> TestClient:
    """Force-403 for the entire scope by raising in require_admin override."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user

    def _admin_check() -> User:
        if user.role != UserRole.admin:
            raise HTTPException(status_code=403, detail="Только для администратора")
        return user

    app.dependency_overrides[require_admin] = _admin_check
    return TestClient(app)


def _make_note(db: Session, **kw) -> ReleaseNote:
    defaults = dict(
        note_type="improvement", section="general",
        title="T", description="D",
    )
    defaults.update(kw)
    n = ReleaseNote(**defaults)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _teardown() -> None:
    app.dependency_overrides.clear()


def test_drafts_admin_only(testclient_db_session: Session):
    manager = _seed_user(testclient_db_session, role=UserRole.manager)
    try:
        r = _client_as_manager(testclient_db_session, manager).get(
            "/api/v1/admin/release-notes/drafts"
        )
        assert r.status_code == 403
    finally:
        _teardown()


def test_admin_list_drafts(testclient_db_session: Session):
    admin = _seed_user(testclient_db_session)
    _make_note(testclient_db_session, title="Draft")
    try:
        r = _client_admin(testclient_db_session, admin).get(
            "/api/v1/admin/release-notes/drafts"
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["version"] is None
        assert body[0]["title"] == "Draft"
    finally:
        _teardown()


def test_admin_create_note(testclient_db_session: Session):
    admin = _seed_user(testclient_db_session)
    try:
        r = _client_admin(testclient_db_session, admin).post(
            "/api/v1/admin/release-notes",
            json={
                "note_type": "fix",
                "section": "sync",
                "title": "Кнопка работает",
                "description": "Тестовый фикс",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["title"] == "Кнопка работает"
        assert body["version"] is None
    finally:
        _teardown()


def test_admin_create_rejects_unknown_type(testclient_db_session: Session):
    admin = _seed_user(testclient_db_session)
    try:
        r = _client_admin(testclient_db_session, admin).post(
            "/api/v1/admin/release-notes",
            json={
                "note_type": "wat", "section": "general",
                "title": "X", "description": "Y",
            },
        )
        assert r.status_code == 400
    finally:
        _teardown()


def test_admin_update_note(testclient_db_session: Session):
    admin = _seed_user(testclient_db_session)
    n = _make_note(testclient_db_session, title="Old")
    try:
        r = _client_admin(testclient_db_session, admin).patch(
            f"/api/v1/admin/release-notes/{n.id}",
            json={"title": "New title", "is_hidden": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["title"] == "New title"
        assert body["is_hidden"] is True
    finally:
        _teardown()


def test_admin_delete_note(testclient_db_session: Session):
    admin = _seed_user(testclient_db_session)
    n = _make_note(testclient_db_session)
    try:
        r = _client_admin(testclient_db_session, admin).delete(
            f"/api/v1/admin/release-notes/{n.id}"
        )
        assert r.status_code == 204
        assert (
            testclient_db_session.query(ReleaseNote).filter_by(id=n.id).first()
            is None
        )
    finally:
        _teardown()


def test_admin_publish_drafts(testclient_db_session: Session):
    admin = _seed_user(testclient_db_session)
    _make_note(testclient_db_session, title="A")
    _make_note(testclient_db_session, title="B", note_type="new")
    try:
        r = _client_admin(testclient_db_session, admin).post(
            "/api/v1/admin/release-notes/publish",
            json={"version": "v1.2.0"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["published_count"] == 2
        notes = testclient_db_session.query(ReleaseNote).all()
        assert all(n.version == "v1.2.0" for n in notes)
    finally:
        _teardown()


def test_admin_publish_no_drafts_returns_400(testclient_db_session: Session):
    admin = _seed_user(testclient_db_session)
    try:
        r = _client_admin(testclient_db_session, admin).post(
            "/api/v1/admin/release-notes/publish",
            json={"version": "v1.2.0"},
        )
        assert r.status_code == 400
    finally:
        _teardown()


def test_admin_publish_rejects_bad_version_format(testclient_db_session: Session):
    admin = _seed_user(testclient_db_session)
    _make_note(testclient_db_session)
    try:
        r = _client_admin(testclient_db_session, admin).post(
            "/api/v1/admin/release-notes/publish",
            json={"version": "v1.2.0-rc1"},
        )
        assert r.status_code == 400
    finally:
        _teardown()


def test_admin_delete_version_reverts_to_drafts(testclient_db_session: Session):
    admin = _seed_user(testclient_db_session)
    _make_note(testclient_db_session, version="v1.5.0")
    try:
        r = _client_admin(testclient_db_session, admin).delete(
            "/api/v1/admin/release-notes/version/v1.5.0"
        )
        assert r.status_code == 204
        notes = testclient_db_session.query(ReleaseNote).all()
        assert all(n.version is None for n in notes)
    finally:
        _teardown()
