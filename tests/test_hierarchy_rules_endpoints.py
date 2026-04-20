"""Integration tests for /hierarchy-rules CRUD."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db


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


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _create(client: TestClient, payload: dict) -> dict:
    resp = client.post("/api/v1/hierarchy-rules", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestHierarchyRulesCrud:
    def test_list_returns_seeded_rules_ordered_by_priority(self, client):
        _create(client, {"priority": 50, "project_key": "ORD1", "issue_type": None,
                 "require_no_parent": False, "is_container": True, "is_enabled": True})
        _create(client, {"priority": 10, "project_key": "ORD2", "issue_type": None,
                 "require_no_parent": False, "is_container": True, "is_enabled": True})
        resp = client.get("/api/v1/hierarchy-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        priorities = [r["priority"] for r in data]
        assert priorities == sorted(priorities)

    def test_create_and_list(self, client):
        before = client.get("/api/v1/hierarchy-rules").json()
        created = _create(client, {
            "priority": 200,
            "project_key": "TEST",
            "issue_type": None,
            "require_no_parent": False,
            "is_container": True,
            "is_enabled": True,
            "description": "test rule",
        })
        assert created["project_key"] == "TEST"
        after = client.get("/api/v1/hierarchy-rules").json()
        assert len(after) == len(before) + 1

    def test_patch_partial(self, client):
        created = _create(client, {
            "priority": 300, "project_key": "PATCH", "issue_type": None,
            "require_no_parent": False, "is_container": True, "is_enabled": True,
        })
        resp = client.patch(
            f"/api/v1/hierarchy-rules/{created['id']}",
            json={"is_container": False, "description": "flipped"},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["is_container"] is False
        assert updated["description"] == "flipped"
        assert updated["project_key"] == "PATCH"

    def test_delete(self, client):
        created = _create(client, {
            "priority": 400, "project_key": "DEL", "issue_type": None,
            "require_no_parent": False, "is_container": True, "is_enabled": True,
        })
        resp = client.delete(f"/api/v1/hierarchy-rules/{created['id']}")
        assert resp.status_code == 200
        resp = client.get("/api/v1/hierarchy-rules")
        assert not any(r["id"] == created["id"] for r in resp.json())

    def test_reorder_writes_stepped_priorities(self, client):
        a = _create(client, {"priority": 500, "project_key": "A", "issue_type": None,
                     "require_no_parent": False, "is_container": True, "is_enabled": True})
        b = _create(client, {"priority": 501, "project_key": "B", "issue_type": None,
                     "require_no_parent": False, "is_container": True, "is_enabled": True})
        c = _create(client, {"priority": 502, "project_key": "C", "issue_type": None,
                     "require_no_parent": False, "is_container": True, "is_enabled": True})
        resp = client.post(
            "/api/v1/hierarchy-rules/reorder",
            json={"ids": [c["id"], a["id"], b["id"]]},
        )
        assert resp.status_code == 200
        data = resp.json()
        by_id = {r["id"]: r["priority"] for r in data}
        assert by_id[c["id"]] == 10
        assert by_id[a["id"]] == 20
        assert by_id[b["id"]] == 30

    def test_negative_priority_rejected(self, client):
        resp = client.post("/api/v1/hierarchy-rules", json={
            "priority": -1, "project_key": "X", "issue_type": None,
            "require_no_parent": False, "is_container": True, "is_enabled": True,
        })
        assert resp.status_code == 422

    def test_delete_unknown_404(self, client):
        resp = client.delete("/api/v1/hierarchy-rules/nonexistent-id")
        assert resp.status_code == 404
