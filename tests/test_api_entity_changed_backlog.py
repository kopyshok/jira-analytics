"""Проверяем, что мутирующие backlog endpoints публикуют entity_changed."""
import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.event_bus import get_event_bus


@pytest.fixture
def db_session():
    """Session backed by StaticPool so TestClient shares the same SQLite connection."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401 – register all models before create_all
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_client(db, mock_bus):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: mock_bus
    return TestClient(app)


def _teardown():
    app.dependency_overrides.clear()


def _seed_item(db):
    from app.models import BacklogItem
    item = BacklogItem(id="bi-x", title="Test", estimate_hours=5)
    db.add(item)
    db.commit()
    return item


def test_create_backlog_item_publishes_backlog(db_session):
    mock_bus = AsyncMock()
    client = _make_client(db_session, mock_bus)
    try:
        r = client.post("/api/v1/backlog", json={"title": "New item"})
        assert r.status_code == 201, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["backlog"]}
    )


def test_update_backlog_item_publishes_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_item(db_session)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.patch(f"/api/v1/backlog/{item.id}", json={"title": "Updated"})
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["backlog"]}
    )


def test_archive_backlog_item_publishes_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_item(db_session)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.post(f"/api/v1/backlog/{item.id}/archive")
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["backlog"]}
    )


def test_restore_backlog_item_publishes_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_item(db_session)
    item.archived_at = datetime.datetime.utcnow()
    db_session.commit()
    client = _make_client(db_session, mock_bus)
    try:
        r = client.post(f"/api/v1/backlog/{item.id}/restore")
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["backlog"]}
    )
