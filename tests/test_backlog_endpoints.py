"""Tests for backlog PATCH endpoint — priority field."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.services.event_bus import get_event_bus


def _make_client(db):
    mock_bus = AsyncMock()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: mock_bus
    return TestClient(app)


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_event_bus, None)


def _create_item(client, title="Test initiative") -> dict:
    resp = client.post("/api/v1/backlog", json={"title": title})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def test_patch_backlog_priority(testclient_db_session):
    """PATCH priority=3 stores and returns the new value."""
    client = _make_client(testclient_db_session)
    try:
        item = _create_item(client)
        item_id = item["id"]

        resp = client.patch(f"/api/v1/backlog/{item_id}", json={"priority": 3})
        assert resp.status_code == 200, resp.text
        assert resp.json()["priority"] == 3

        resp2 = client.get(f"/api/v1/backlog/{item_id}")
        assert resp2.status_code == 200, resp2.text
        assert resp2.json()["priority"] == 3
    finally:
        _teardown()


def test_patch_backlog_priority_clear(testclient_db_session):
    """PATCH priority=null clears the priority."""
    client = _make_client(testclient_db_session)
    try:
        item = _create_item(client, "Init with priority")
        item_id = item["id"]

        client.patch(f"/api/v1/backlog/{item_id}", json={"priority": 5})

        resp = client.patch(f"/api/v1/backlog/{item_id}", json={"priority": None})
        assert resp.status_code == 200, resp.text
        assert resp.json()["priority"] is None
    finally:
        _teardown()


def test_patch_backlog_priority_validation(testclient_db_session):
    """PATCH with out-of-range priority (15) must return 422."""
    client = _make_client(testclient_db_session)
    try:
        item = _create_item(client, "Init for validation")
        item_id = item["id"]

        resp = client.patch(f"/api/v1/backlog/{item_id}", json={"priority": 15})
        assert resp.status_code == 422, resp.text
    finally:
        _teardown()
