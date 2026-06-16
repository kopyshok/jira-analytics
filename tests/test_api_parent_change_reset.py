"""When PM confirms a category, parent_changed flag is cleared and
category_context is re-baselined to the current parent."""

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


def test_set_category_clears_parent_changed(client, db_session):
    from app.models import Project, Issue

    project = Project(jira_project_id="p-pc", key="PC", name="PC")
    db_session.add(project); db_session.flush()
    parent = Issue(jira_issue_id="j-pcp", key="PC-1", summary="p",
                   issue_type="Epic", status="Open", project_id=project.id,
                   assigned_category="tech_debt")
    db_session.add(parent); db_session.flush()
    issue = Issue(jira_issue_id="j-pci", key="PC-2", summary="c",
                  issue_type="Task", status="Open", project_id=project.id,
                  parent_id=parent.id, parent_changed=True,
                  category_verified=False, category_context="meetings",
                  category_context_key="OLD-1")
    db_session.add(issue); db_session.flush()
    iid = issue.id

    resp = client.put(f"/api/v1/issues/{iid}/category", json={"category_code": "tech_debt"})
    assert resp.status_code == 200

    db_session.expire_all()
    refreshed = db_session.get(Issue, iid)
    assert refreshed.parent_changed is False
    assert refreshed.category_context == "tech_debt"
    assert refreshed.category_context_key == "PC-1"
