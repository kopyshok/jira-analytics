"""Проверяем, что batch-category публикует entity_changed."""
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.services.event_bus import get_event_bus


def _make_client(db, mock_bus):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: mock_bus
    return TestClient(app)


def _teardown():
    app.dependency_overrides.clear()


def _seed_issue(db):
    from app.models import Category, Issue, Project
    cat = Category(id="cat-dev", code="development", label="Dev",
                   color="#000", sort_order=1, is_system=True)
    proj = Project(id="p-ic", jira_project_id="p-ic-j", key="IC",
                   name="IC", is_active=True)
    issue = Issue(id="i-ic", jira_issue_id="i-ic-j", key="IC-1",
                  summary="S", issue_type="Task", status="Open",
                  project_id="p-ic", category="development")
    db.add_all([cat, proj, issue])
    db.commit()
    return issue


def test_batch_category_publishes_issues_and_backlog(testclient_db_session):
    mock_bus = AsyncMock()
    issue = _seed_issue(testclient_db_session)
    client = _make_client(testclient_db_session, mock_bus)
    try:
        r = client.put(
            "/api/v1/issues/batch-category",
            json={"issue_ids": [issue.id], "category_code": "development"},
        )
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["issues", "backlog"]}
    )
