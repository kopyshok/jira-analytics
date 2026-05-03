"""Test PATCH assignee on allocation."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_patch_assignee_not_found():
    resp = client.patch(
        "/api/v1/planning/scenarios/nonexistent/allocations/nonexistent/assignee",
        json={"assignee_employee_id": None},
    )
    assert resp.status_code == 404
