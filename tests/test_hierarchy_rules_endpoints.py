"""Integration tests for /hierarchy-rules CRUD."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create(payload: dict) -> dict:
    resp = client.post("/api/v1/hierarchy-rules", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestHierarchyRulesCrud:
    def test_list_returns_seeded_rules_ordered_by_priority(self, db_session):
        # conftest wipes all tables between tests, so seed from migration may be absent.
        # Create a known rule and verify list is sorted ascending.
        _create({"priority": 50, "project_key": "ORD1", "issue_type": None,
                 "require_no_parent": False, "is_container": True, "is_enabled": True})
        _create({"priority": 10, "project_key": "ORD2", "issue_type": None,
                 "require_no_parent": False, "is_container": True, "is_enabled": True})
        resp = client.get("/api/v1/hierarchy-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        priorities = [r["priority"] for r in data]
        assert priorities == sorted(priorities)

    def test_create_and_list(self, db_session):
        before = client.get("/api/v1/hierarchy-rules").json()
        created = _create({
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

    def test_patch_partial(self, db_session):
        created = _create({
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

    def test_delete(self, db_session):
        created = _create({
            "priority": 400, "project_key": "DEL", "issue_type": None,
            "require_no_parent": False, "is_container": True, "is_enabled": True,
        })
        resp = client.delete(f"/api/v1/hierarchy-rules/{created['id']}")
        assert resp.status_code == 200
        resp = client.get("/api/v1/hierarchy-rules")
        assert not any(r["id"] == created["id"] for r in resp.json())

    def test_reorder_writes_stepped_priorities(self, db_session):
        a = _create({"priority": 500, "project_key": "A", "issue_type": None,
                     "require_no_parent": False, "is_container": True, "is_enabled": True})
        b = _create({"priority": 501, "project_key": "B", "issue_type": None,
                     "require_no_parent": False, "is_container": True, "is_enabled": True})
        c = _create({"priority": 502, "project_key": "C", "issue_type": None,
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

    def test_negative_priority_rejected(self, db_session):
        resp = client.post("/api/v1/hierarchy-rules", json={
            "priority": -1, "project_key": "X", "issue_type": None,
            "require_no_parent": False, "is_container": True, "is_enabled": True,
        })
        assert resp.status_code == 422

    def test_delete_unknown_404(self, db_session):
        resp = client.delete("/api/v1/hierarchy-rules/nonexistent-id")
        assert resp.status_code == 404
