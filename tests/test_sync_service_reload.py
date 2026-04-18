"""Тесты точечной перезагрузки worklog'ов по дате starts."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

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


def test_reload_deletes_only_rows_at_or_after_since(db_session, sample_data):
    async def iter_issues_empty(jql, **_):
        return
        yield  # pragma: no cover

    jira = MagicMock()
    jira.iter_issues = iter_issues_empty
    service = SyncService(db_session, jira_client=jira)

    stats = service.reload_worklogs_since(date(2026, 1, 1))

    assert isinstance(stats, ReloadStats)
    assert stats.deleted == 1
    remaining_ids = {w.jira_worklog_id for w in db_session.query(Worklog).all()}
    assert remaining_ids == {"10"}


def test_reload_repulls_and_inserts_new_rows(db_session, sample_data):
    """Удалили пост-since → перечитали issue'ы из JQL → вставили новые worklog'и."""
    from datetime import timezone

    jira_issue_payload = MagicMock()
    jira_issue_payload.id = "1001"
    jira_issue_payload.key = "PRJ-1"

    worklog_payload = MagicMock()
    worklog_payload.id = "30"
    worklog_payload.started = datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc)
    worklog_payload.time_spent_seconds = 7200
    worklog_payload.author.account_id = "a1"
    worklog_payload.author.display_name = "Иванов"
    worklog_payload.author.email_address = "ivanov@example.com"
    worklog_payload.author.active = True
    worklog_payload.comment = "fix"

    async def iter_issues_mock(jql, **_):
        assert "worklogDate" in jql
        yield jira_issue_payload

    async def iter_worklogs_mock(_):
        yield worklog_payload

    jira = MagicMock()
    jira.iter_issues = iter_issues_mock
    jira.iter_worklogs_for_issue = iter_worklogs_mock

    service = SyncService(db_session, jira_client=jira)
    stats = service.reload_worklogs_since(date(2026, 1, 1))

    assert stats.issues_scanned == 1
    assert stats.worklogs_inserted == 1
    keys = {w.jira_worklog_id for w in db_session.query(Worklog).all()}
    assert keys == {"10", "30"}  # old kept, new inserted


def test_reload_skips_unknown_issues(db_session, sample_data):
    """Если Jira вернула issue, которой нет в локальной БД — пропускаем."""
    jira_issue_payload = MagicMock()
    jira_issue_payload.id = "9999"  # not in DB
    jira_issue_payload.key = "UNK-1"

    async def iter_issues_mock(jql, **_):
        yield jira_issue_payload

    async def iter_worklogs_mock(_):
        raise AssertionError("should not be called for unknown issue")
        yield  # pragma: no cover

    jira = MagicMock()
    jira.iter_issues = iter_issues_mock
    jira.iter_worklogs_for_issue = iter_worklogs_mock

    service = SyncService(db_session, jira_client=jira)
    stats = service.reload_worklogs_since(date(2026, 1, 1))

    assert stats.issues_scanned == 0  # unknown not counted
    assert stats.worklogs_inserted == 0
