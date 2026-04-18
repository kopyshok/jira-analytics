"""Тесты точечной перезагрузки worklog'ов по дате starts."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.connectors.schemas import JiraWorklogAuthorSchema, JiraWorklogSchema
from app.models import Employee, Issue, Project, Worklog
from app.services.sync_service import SyncService, ReloadStats


@pytest.fixture
def sample_data(db_session):
    project = Project(id="p1", jira_project_id="100", key="PRJ", name="PRJ")
    employee = Employee(
        id="e1", jira_account_id="a1", display_name="Иванов",
        email="ivanov@example.com", is_active=True,
    )
    issue = Issue(
        id="i1", jira_issue_id="1001", key="PRJ-1", summary="x",
        project_id=project.id, issue_type="Task", status="В работе",
    )
    db_session.add_all([project, employee, issue])
    db_session.flush()

    old = Worklog(
        id="w_old", jira_worklog_id="10",
        issue_id=issue.id, employee_id=employee.id,
        started_at=datetime(2025, 12, 15, 10, 0),
        hours=4.0, time_spent_seconds=14400,
    )
    new = Worklog(
        id="w_new", jira_worklog_id="20",
        issue_id=issue.id, employee_id=employee.id,
        started_at=datetime(2026, 1, 5, 10, 0),
        hours=3.0, time_spent_seconds=10800,
    )
    db_session.add_all([old, new])
    db_session.commit()
    return {"project": project, "employee": employee, "issue": issue,
            "old": old, "new": new}


async def test_reload_deletes_only_rows_at_or_after_since(db_session, sample_data):
    async def iter_issues_empty(jql, **_):
        return
        yield  # pragma: no cover

    jira = MagicMock()
    jira.iter_issues = iter_issues_empty
    service = SyncService(db_session, jira_client=jira)

    stats = await service.reload_worklogs_since(date(2026, 1, 1))

    assert isinstance(stats, ReloadStats)
    assert stats.deleted == 1
    remaining_ids = {w.jira_worklog_id for w in db_session.query(Worklog).all()}
    assert remaining_ids == {"10"}


async def test_reload_repulls_and_inserts_new_rows(db_session, sample_data):
    """Удалили пост-since → перечитали issue'ы из JQL → вставили новые worklog'и."""
    jira_issue_payload = SimpleNamespace(id="1001", key="PRJ-1")

    author = JiraWorklogAuthorSchema(
        accountId="a1",
        displayName="Иванов",
        emailAddress="ivanov@example.com",
    )
    worklog_payload = JiraWorklogSchema(
        id="30",
        issueId="1001",
        author=author,
        started="2026-02-10T09:00:00.000+0000",
        timeSpentSeconds=7200,
        comment="fix",
        created="2026-02-10T09:00:00.000+0000",
        updated="2026-02-10T09:00:00.000+0000",
    )

    async def iter_issues_mock(jql, **_):
        assert "worklogDate" in jql
        yield jira_issue_payload

    async def iter_worklogs_mock(_):
        yield worklog_payload

    jira = MagicMock()
    jira.iter_issues = iter_issues_mock
    jira.iter_worklogs_for_issue = iter_worklogs_mock

    service = SyncService(db_session, jira_client=jira)
    stats = await service.reload_worklogs_since(date(2026, 1, 1))

    assert stats.issues_scanned == 1
    assert stats.worklogs_inserted == 1
    keys = {w.jira_worklog_id for w in db_session.query(Worklog).all()}
    assert keys == {"10", "30"}  # old kept, new inserted


async def test_reload_skips_unknown_issues(db_session, sample_data):
    """Если Jira вернула issue, которой нет в локальной БД — пропускаем."""
    jira_issue_payload = SimpleNamespace(id="9999", key="UNK-1")  # not in DB

    async def iter_issues_mock(jql, **_):
        yield jira_issue_payload

    async def iter_worklogs_mock(_):
        raise AssertionError("should not be called for unknown issue")
        yield  # pragma: no cover

    jira = MagicMock()
    jira.iter_issues = iter_issues_mock
    jira.iter_worklogs_for_issue = iter_worklogs_mock

    service = SyncService(db_session, jira_client=jira)
    stats = await service.reload_worklogs_since(date(2026, 1, 1))

    assert stats.issues_scanned == 0  # unknown not counted
    assert stats.worklogs_inserted == 0
