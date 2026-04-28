"""Regression: active backlog view must include items with indeterminate Jira status.

RFA-241 had status_category='indeterminate' and was missing from the active tab
because the filter excluded it. Fix: only exclude 'done' from active view;
indeterminate items remain visible until they move to an approved scenario.
"""

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
    app.dependency_overrides.clear()


def test_active_view_includes_indeterminate_jira_status(testclient_db_session):
    """Items linked to an issue with status_category='indeterminate' must appear
    in the active backlog view when they are NOT in an approved scenario."""
    from app.models import BacklogItem, Issue, Project

    db = testclient_db_session
    proj = Project(
        id="p-reg", jira_project_id="p-reg-jira", key="REG", name="REG", is_active=True
    )
    issue = Issue(
        id="i-reg",
        jira_issue_id="i-reg-jira",
        key="REG-241",
        summary="In-progress initiative",
        issue_type="RFA",
        status="В разработке",
        status_category="indeterminate",
        project_id=proj.id,
    )
    item = BacklogItem(
        id="bi-reg-241",
        title="In-progress initiative",
        issue_id=issue.id,
        archived_at=None,
    )
    db.add_all([proj, issue, item])
    db.commit()

    client = _make_client(db)
    try:
        resp = client.get("/api/v1/backlog?view=active")
        assert resp.status_code == 200, resp.text
        ids = [i["id"] for i in resp.json()]
        assert "bi-reg-241" in ids, (
            "BacklogItem linked to an indeterminate-status issue must appear in active view "
            "when it is not allocated to an approved scenario"
        )
    finally:
        _teardown()


def test_active_view_excludes_done_jira_status(testclient_db_session):
    """Items linked to a 'done' issue must NOT appear in active view."""
    from app.models import BacklogItem, Issue, Project

    db = testclient_db_session
    proj = Project(
        id="p-done", jira_project_id="p-done-jira", key="DON", name="DON", is_active=True
    )
    issue = Issue(
        id="i-done",
        jira_issue_id="i-done-jira",
        key="DON-1",
        summary="Completed initiative",
        issue_type="RFA",
        status="Done",
        status_category="done",
        project_id=proj.id,
    )
    item = BacklogItem(
        id="bi-done-1",
        title="Completed initiative",
        issue_id=issue.id,
        archived_at=None,
    )
    db.add_all([proj, issue, item])
    db.commit()

    client = _make_client(db)
    try:
        resp = client.get("/api/v1/backlog?view=active")
        assert resp.status_code == 200, resp.text
        ids = [i["id"] for i in resp.json()]
        assert "bi-done-1" not in ids, (
            "BacklogItem linked to a done-status issue must be excluded from active view"
        )
    finally:
        _teardown()
