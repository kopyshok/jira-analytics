"""Tests for GET/PATCH /api/v1/resource-planning/preferences."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth_deps import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_user(db_session, email: str) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash="x",
        display_name=email,
        role=UserRole.admin,
        is_active=True,
        selected_teams_raw="[]",
        selected_period_raw="{}",
        analytics_columns_raw="[]",
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client_factory(db_session):
    """Возвращает фабрику TestClient для произвольного пользователя."""

    def _factory(user: User) -> TestClient:
        def _get_db():
            yield db_session

        app.dependency_overrides[get_db] = _get_db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield _factory
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_get_default_preferences_returns_zero_state(db_session, client_factory):
    user = _make_user(db_session, "u1@example.com")
    client = client_factory(user)
    r = client.get("/api/v1/resource-planning/preferences")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hide_weekends"] is False
    assert body["collapsed_initiative_ids"] == []
    assert body["show_relay"] is True


def test_patch_preferences_persists(db_session, client_factory):
    user = _make_user(db_session, "u2@example.com")
    client = client_factory(user)
    r = client.patch(
        "/api/v1/resource-planning/preferences",
        json={
            "hide_weekends": True,
            "collapsed_initiative_ids": ["i1", "i2"],
            "view_mode": "phases",
            "show_relay": False,
        },
    )
    assert r.status_code == 200, r.text

    r2 = client.get("/api/v1/resource-planning/preferences")
    body = r2.json()
    assert body["hide_weekends"] is True
    assert body["collapsed_initiative_ids"] == ["i1", "i2"]
    assert body["view_mode"] == "phases"
    assert body["show_relay"] is False


def test_preferences_isolated_per_user(db_session, client_factory):
    user_a = _make_user(db_session, "ua@example.com")
    user_b = _make_user(db_session, "ub@example.com")

    client_a = client_factory(user_a)
    client_a.patch(
        "/api/v1/resource-planning/preferences",
        json={"hide_weekends": True, "collapsed_initiative_ids": []},
    )

    client_b = client_factory(user_b)
    r = client_b.get("/api/v1/resource-planning/preferences")
    assert r.json()["hide_weekends"] is False
