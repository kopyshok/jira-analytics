"""Tests for /issues/bulk/* endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_bulk_preview_only_parent_changed(client, db_session):
    from app.models import Project, Issue
    project = Project(jira_project_id="p-bp", key="BP", name="BP")
    db_session.add(project); db_session.flush()
    moved = Issue(jira_issue_id="j-bm", key="BP-1", summary="moved",
                  issue_type="Task", status="Open", project_id=project.id,
                  parent_changed=True, category_context="tech_debt",
                  category_context_key="OLD-1")
    plain = Issue(jira_issue_id="j-bp", key="BP-2", summary="plain",
                  issue_type="Task", status="Open", project_id=project.id)
    db_session.add_all([moved, plain]); db_session.flush()
    resp = client.post("/api/v1/issues/bulk/preview",
                       json={"filters": {"only_parent_changed": True}, "limit": 50})
    assert resp.status_code == 200
    data = resp.json()
    keys = {i["key"] for i in data["items"]}
    assert "BP-1" in keys and "BP-2" not in keys
    assert next(i for i in data["items"] if i["key"] == "BP-1")["parent_changed"] is True
