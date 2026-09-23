"""Правка правил иерархии рассылает entity_changed: меняются бэклог, сценарии, аналитика."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import HierarchyRule
from app.services.event_bus import get_event_bus

EVENT = {"type": "entity_changed", "entities": ["backlog", "planning", "analytics"]}


@pytest.fixture
def bus():
    return AsyncMock()


@pytest.fixture
def client(testclient_db_session, bus):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    app.dependency_overrides[get_event_bus] = lambda: bus
    yield TestClient(app)
    app.dependency_overrides.clear()


def _rule(db) -> str:
    rule = HierarchyRule(priority=10, project_key="RFA", is_container=True, is_enabled=True)
    db.add(rule)
    db.commit()
    return rule.id


def test_create_publishes(client, bus):
    r = client.post("/api/v1/hierarchy-rules", json={"priority": 1, "is_container": True})
    assert r.status_code == 201, r.text
    bus.publish.assert_called_once_with(EVENT)


def test_update_publishes(client, bus, testclient_db_session):
    rid = _rule(testclient_db_session)
    r = client.patch(f"/api/v1/hierarchy-rules/{rid}", json={"is_enabled": False})
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(EVENT)


def test_delete_publishes(client, bus, testclient_db_session):
    rid = _rule(testclient_db_session)
    r = client.delete(f"/api/v1/hierarchy-rules/{rid}")
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(EVENT)


def test_reorder_publishes(client, bus, testclient_db_session):
    rid = _rule(testclient_db_session)
    r = client.post("/api/v1/hierarchy-rules/reorder", json={"ids": [rid]})
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(EVENT)
