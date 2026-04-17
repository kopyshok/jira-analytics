"""Issue-config endpoint tests — category assignment and include flag."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Issue, Project


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def project_and_issues(db_session):
    project = Project(
        jira_project_id="10001",
        key="TEST",
        name="Test project",
        is_active=True,
    )
    db_session.add(project)
    db_session.flush()

    issues = [
        Issue(
            jira_issue_id=f"100{i}",
            key=f"TEST-{i}",
            summary=f"Issue {i}",
            issue_type="Task",
            status="Open",
            project_id=project.id,
            include_in_analysis=True,
        )
        for i in range(1, 4)
    ]
    db_session.add_all(issues)
    db_session.flush()
    return project, issues


def test_set_category_archive_auto_excludes(client, project_and_issues, db_session):
    _, issues = project_and_issues
    target = issues[0]

    response = client.put(
        f"/api/v1/issues/{target.id}/category",
        json={"category_code": "archive"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["assigned_category"] == "archive"
    assert body["include_in_analysis"] is False
    assert body["auto_excluded"] is True

    db_session.expire_all()
    persisted = db_session.get(Issue, target.id)
    assert persisted.include_in_analysis is False


def test_set_category_non_archive_keeps_include(client, project_and_issues, db_session):
    _, issues = project_and_issues
    target = issues[0]

    response = client.put(
        f"/api/v1/issues/{target.id}/category",
        json={"category_code": "development"},
    )

    body = response.json()
    assert body["assigned_category"] == "development"
    assert body["include_in_analysis"] is True
    assert body["auto_excluded"] is False

    db_session.expire_all()
    persisted = db_session.get(Issue, target.id)
    assert persisted.include_in_analysis is True


def test_set_category_archive_already_excluded_does_not_re_report(client, project_and_issues, db_session):
    _, issues = project_and_issues
    target = issues[0]
    target.include_in_analysis = False
    db_session.flush()

    response = client.put(
        f"/api/v1/issues/{target.id}/category",
        json={"category_code": "archive"},
    )

    body = response.json()
    assert body["assigned_category"] == "archive"
    assert body["include_in_analysis"] is False
    assert body["auto_excluded"] is False


def test_set_category_to_none_leaves_include_alone(client, project_and_issues, db_session):
    _, issues = project_and_issues
    target = issues[0]
    target.assigned_category = "archive"
    target.include_in_analysis = False
    db_session.flush()

    response = client.put(
        f"/api/v1/issues/{target.id}/category",
        json={"category_code": None},
    )

    body = response.json()
    assert body["assigned_category"] is None
    assert body["include_in_analysis"] is False


def test_batch_category_archive_reports_archived_ids(client, project_and_issues, db_session):
    _, issues = project_and_issues
    ids = [issues[0].id, issues[1].id]

    response = client.put(
        "/api/v1/issues/batch-category",
        json={"issue_ids": ids, "category_code": "archive"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 2
    assert sorted(body["archived_ids"]) == sorted(ids)

    for issue_id in ids:
        issue = db_session.get(Issue, issue_id)
        assert issue.assigned_category == "archive"
        assert issue.include_in_analysis is False


def test_batch_category_non_archive_returns_empty_archived_ids(client, project_and_issues):
    _, issues = project_and_issues

    response = client.put(
        "/api/v1/issues/batch-category",
        json={"issue_ids": [issues[0].id], "category_code": "development"},
    )

    body = response.json()
    assert body["updated"] == 1
    assert body["archived_ids"] == []
