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


def test_quarterly_view_excludes_cancelled_status(testclient_db_session):
    """Quarterly tab must hide tasks with cancel-like status (Отменено)
    even if status_category is not yet 'done'."""
    from app.models import BacklogItem, Issue, Project

    db = testclient_db_session
    proj = Project(
        id="p-cx", jira_project_id="p-cx-jira", key="CX", name="CX", is_active=True
    )
    issue = Issue(
        id="i-cx-cancel",
        jira_issue_id="i-cx-cancel-jira",
        key="CX-1",
        summary="Cancelled quarterly",
        issue_type="Цель",
        status="Отменено",
        status_category="done",
        project_id=proj.id,
        category="quarterly_tasks",
    )
    item = BacklogItem(
        id="bi-cx-cancel", title="Cancelled quarterly", issue_id=issue.id, archived_at=None
    )
    db.add_all([proj, issue, item])
    db.commit()

    client = _make_client(db)
    try:
        resp = client.get("/api/v1/backlog?view=quarterly")
        assert resp.status_code == 200, resp.text
        ids = [i["id"] for i in resp.json()]
        assert "bi-cx-cancel" not in ids, (
            "Cancelled quarterly task must not appear in Активные tab"
        )
    finally:
        _teardown()


def test_quarterly_view_keeps_done_quarterly_task(testclient_db_session):
    """Done (Закрыт) quarterly task must remain visible in Активные —
    выполненная по плану задача, не cancel."""
    from app.models import BacklogItem, Issue, Project

    db = testclient_db_session
    proj = Project(
        id="p-dq", jira_project_id="p-dq-jira", key="DQ", name="DQ", is_active=True
    )
    issue = Issue(
        id="i-dq-done",
        jira_issue_id="i-dq-done-jira",
        key="DQ-1",
        summary="Completed quarterly",
        issue_type="Цель",
        status="Закрыт",
        status_category="done",
        project_id=proj.id,
        category="quarterly_tasks",
    )
    item = BacklogItem(
        id="bi-dq-done", title="Completed quarterly", issue_id=issue.id, archived_at=None
    )
    db.add_all([proj, issue, item])
    db.commit()

    client = _make_client(db)
    try:
        resp = client.get("/api/v1/backlog?view=quarterly")
        assert resp.status_code == 200, resp.text
        ids = [i["id"] for i in resp.json()]
        assert "bi-dq-done" in ids, (
            "Done quarterly task must stay in Активные as part of the plan"
        )
    finally:
        _teardown()


def test_active_view_includes_initiative_with_epic_parent(testclient_db_session):
    """Initiative under an Epic parent must show up in Бэклог tab.
    Regression: parent_id IS NULL filter previously hid all child tasks
    including legitimate initiatives nested under container Epics."""
    from app.models import BacklogItem, Issue, Project

    db = testclient_db_session
    proj = Project(
        id="p-init", jira_project_id="p-init-jira", key="ITL", name="ITL", is_active=True
    )
    epic = Issue(
        id="i-epic",
        jira_issue_id="i-epic-jira",
        key="ITL-EPIC",
        summary="Epic",
        issue_type="Epic",
        status="In progress",
        status_category="indeterminate",
        project_id=proj.id,
    )
    init = Issue(
        id="i-init",
        jira_issue_id="i-init-jira",
        key="ITL-300",
        summary="Initiative under epic",
        issue_type="ИТ-задача",
        status="В работе",
        status_category="indeterminate",
        project_id=proj.id,
        parent_id=epic.id,
        category="initiatives_rfa",
    )
    item = BacklogItem(
        id="bi-init-300", title="Initiative under epic", issue_id=init.id, archived_at=None
    )
    db.add_all([proj, epic, init, item])
    db.commit()

    client = _make_client(db)
    try:
        resp = client.get("/api/v1/backlog?view=active")
        assert resp.status_code == 200, resp.text
        ids = [i["id"] for i in resp.json()]
        assert "bi-init-300" in ids, (
            "Initiative with Epic parent must appear in Бэклог tab"
        )
    finally:
        _teardown()


def test_archived_view_excludes_done_quarterly(testclient_db_session):
    """Done quarterly task в approved scenario НЕ должна попадать в Архив —
    остаётся в Активных как выполненная по плану."""
    from app.models import BacklogItem, Issue, Project

    db = testclient_db_session
    proj = Project(
        id="p-aq", jira_project_id="p-aq-jira", key="AQ", name="AQ", is_active=True
    )
    issue = Issue(
        id="i-aq-done",
        jira_issue_id="i-aq-done-jira",
        key="AQ-1",
        summary="Done quarterly",
        issue_type="Цель",
        status="Закрыт",
        status_category="done",
        project_id=proj.id,
        category="quarterly_tasks",
    )
    item = BacklogItem(
        id="bi-aq-done", title="Done quarterly", issue_id=issue.id, archived_at=None
    )
    db.add_all([proj, issue, item])
    db.commit()

    client = _make_client(db)
    try:
        resp = client.get("/api/v1/backlog?view=archived")
        assert resp.status_code == 200, resp.text
        ids = [i["id"] for i in resp.json()]
        assert "bi-aq-done" not in ids, (
            "Done quarterly task must not auto-archive — это часть утверждённого плана"
        )
    finally:
        _teardown()


def test_archived_item_has_quarter_label(testclient_db_session):
    """Archived backlog item allocated to approved scenario has quarter_label."""
    from datetime import datetime

    from app.models import BacklogItem, PlanningScenario, ScenarioAllocation

    db = testclient_db_session
    sc = PlanningScenario(
        id="sc-ql-1", name="Q2 Test", quarter="Q2", year=2026,
        status="approved", team="T1",
    )
    db.add(sc)
    bi = BacklogItem(id="bi-ql-1", title="Test item", archived_at=datetime(2026, 4, 1))
    db.add(bi)
    db.flush()
    db.add(ScenarioAllocation(
        id="sa-ql-1", scenario_id="sc-ql-1", backlog_item_id="bi-ql-1",
        included_flag=True, sort_order=0,
    ))
    db.commit()

    client = _make_client(db)
    try:
        resp = client.get("/api/v1/backlog?view=archived")
        assert resp.status_code == 200
        item = next((i for i in resp.json() if i["id"] == "bi-ql-1"), None)
        assert item is not None
        assert item["quarter_label"] == "2 кв. 2026"
    finally:
        _teardown()
