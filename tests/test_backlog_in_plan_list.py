"""Служебный эпик в списке целевых задач — только дочерней строкой своей RFA."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, HierarchyRule, Issue, Project
from app.services.backlog_service import BacklogService


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed(db) -> dict[str, str]:
    db.add_all([
        HierarchyRule(priority=5, project_key="RFA", issue_type="Эпик", require_no_parent=False,
                      require_parent=True, is_container=False, is_enabled=True, description="svc"),
        HierarchyRule(priority=10, project_key="RFA", issue_type=None, require_no_parent=False,
                      require_parent=False, is_container=True, is_enabled=True),
        Project(id="p-rfa", key="RFA", jira_project_id="jp-rfa", name="RFA"),
    ])
    db.flush()
    db.add_all([
        Issue(id="i-rfa", key="RFA-1", jira_issue_id="j1", summary="RFA", issue_type="RFA",
              status="Open", project_id="p-rfa", category="initiatives_rfa", team="T1"),
        Issue(id="i-disc", key="RFA-2", jira_issue_id="j2", summary="Дискавери", issue_type="Эпик",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa", team="T1"),
    ])
    db.flush()
    svc = BacklogService(db)
    svc.sync_from_issue(db.get(Issue, "i-rfa"))
    svc.sync_from_issue(db.get(Issue, "i-disc"))
    db.commit()
    return {bi.issue_id: bi.id for bi in db.query(BacklogItem).all()}


def _all_ids(rows) -> set[str]:
    return {r["id"] for r in rows} | {c["id"] for r in rows for c in r.get("children", [])}


def test_service_epic_shown_as_child_row_off_plan(client, testclient_db_session):
    ids = _seed(testclient_db_session)
    rows = client.get("/api/v1/backlog", params={"view": "active"}).json()
    roots = {r["id"]: r for r in rows}
    assert ids["i-disc"] not in roots, "Дискавери — не инициатива, корнем не показывается"
    kids = {c["id"]: c for c in roots[ids["i-rfa"]]["children"]}
    assert kids[ids["i-disc"]]["included_in_planning"] is False


def test_service_epic_hidden_when_parent_not_listed(client, testclient_db_session):
    ids = _seed(testclient_db_session)
    parent = testclient_db_session.get(BacklogItem, ids["i-rfa"])
    parent.archived_at = datetime.utcnow()
    testclient_db_session.commit()
    rows = client.get("/api/v1/backlog", params={"view": "active"}).json()
    assert ids["i-disc"] not in _all_ids(rows)
