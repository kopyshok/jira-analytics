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
    jira = MagicMock()
    jira.iter_issues = AsyncMock(return_value=iter([]))  # no new data
    service = SyncService(db_session, jira_client=jira)

    stats = service.reload_worklogs_since(date(2026, 1, 1))

    assert isinstance(stats, ReloadStats)
    assert stats.deleted == 1
    remaining_ids = {w.jira_worklog_id for w in db_session.query(Worklog).all()}
    assert remaining_ids == {"10"}
