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


def test_bulk_accept_suggestions_clears_parent_changed(client, db_session):
    """Подтверждение через bulk «принять подсказки» снимает пометку переезда
    и сдвигает точку отсчёта — иначе следующий пересчёт вернёт задачу в стопку."""
    from app.models import Project, Issue
    from app.services.mapping_service import MappingService

    project = Project(jira_project_id="p-as", key="AS", name="AS")
    db_session.add(project); db_session.flush()
    parent = Issue(jira_issue_id="j-asp", key="AS-1", summary="p",
                   issue_type="Epic", status="Open", project_id=project.id,
                   assigned_category="tech_debt")
    db_session.add(parent); db_session.flush()
    issue = Issue(jira_issue_id="j-asi", key="AS-2", summary="c",
                  issue_type="Task", status="Open", project_id=project.id,
                  parent_id=parent.id, category="tech_debt",
                  parent_changed=True, category_verified=False,
                  category_context="meetings", category_context_key="OLD-1")
    db_session.add(issue); db_session.flush()
    iid = issue.id

    resp = client.post("/api/v1/issues/bulk/accept-suggestions",
                       json={"filters": {"only_parent_changed": True}})
    assert resp.status_code == 200

    db_session.expire_all()
    refreshed = db_session.get(Issue, iid)
    assert refreshed.parent_changed is False
    assert refreshed.category_context == "tech_debt"
    # И повторный пересчёт не возвращает пометку обратно.
    MappingService(db_session).recalculate_issues()
    db_session.expire_all()
    assert db_session.get(Issue, iid).parent_changed is False


def test_bulk_cascade_inherit_clears_parent_changed(client, db_session):
    """Каскадное подтверждение тоже снимает пометку переезда у потомков."""
    from app.models import Project, Issue
    from app.services.mapping_service import MappingService

    project = Project(jira_project_id="p-ci", key="CI", name="CI")
    db_session.add(project); db_session.flush()
    anc = Issue(jira_issue_id="j-cia", key="CI-1", summary="anc",
                issue_type="Epic", status="Open", project_id=project.id,
                assigned_category="tech_debt")
    db_session.add(anc); db_session.flush()
    child = Issue(jira_issue_id="j-cic", key="CI-2", summary="ch",
                  issue_type="Task", status="Open", project_id=project.id,
                  parent_id=anc.id, parent_changed=True, category_verified=False,
                  category_context="meetings", category_context_key="OLD-2")
    db_session.add(child); db_session.flush()
    cid = child.id

    resp = client.post("/api/v1/issues/bulk/cascade-inherit",
                       json={"ancestor_ids": [anc.id]})
    assert resp.status_code == 200

    db_session.expire_all()
    refreshed = db_session.get(Issue, cid)
    assert refreshed.parent_changed is False
    assert refreshed.category_context == "tech_debt"
    MappingService(db_session).recalculate_issues()
    db_session.expire_all()
    assert db_session.get(Issue, cid).parent_changed is False
