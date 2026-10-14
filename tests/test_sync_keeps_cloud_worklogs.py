"""Синк никогда не удаляет ворклоги с облачным id («cloud:…»).

После переезда на новую Jira у задач, которых в ней нет (оставлены по
решению, проект не переехал), ворклоги сохранены с префиксом «cloud:»: из
Jira они больше не придут, удаление потеряло бы их навсегда.
"""
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models import Employee, EmployeeTeam, Issue, Project, Worklog
from app.services.sync_service import SyncService

STARTED = datetime(2026, 3, 1, 10)


@pytest.fixture
def world(db_session):
    project = Project(id="p-1", jira_project_id="10000", key="PRJ", name="PRJ")
    employee = Employee(
        id="e-1", jira_account_id="acc-1", jira_username="login-1", display_name="A", is_active=True,
    )
    issue = Issue(
        id="i-1", jira_issue_id="20000", key="PRJ-1", summary="s",
        project_id=project.id, issue_type="Task", status="Open",
    )
    db_session.add_all([project, employee, issue])
    db_session.add(EmployeeTeam(id="et-1", employee_id=employee.id, team="Alpha", is_primary=True))
    for wl_id in ("cloud:850609", "wl-stale"):
        db_session.add(Worklog(
            jira_worklog_id=wl_id, issue_id=issue.id, employee_id=employee.id,
            started_at=STARTED, hours=1.0, time_spent_seconds=3600,
        ))
    db_session.commit()
    return issue


def _remaining(db_session) -> set[str]:
    return {wl_id for (wl_id,) in db_session.query(Worklog.jira_worklog_id).all()}


def _fake_issue():
    return SimpleNamespace(
        id="20000", key="PRJ-1",
        fields=SimpleNamespace(
            summary="s",
            issuetype=SimpleNamespace(name="Task"),
            status=SimpleNamespace(name="Open", statusCategory=SimpleNamespace(key="new")),
            project=SimpleNamespace(id="10000", key="PRJ", name="PRJ"),
        ),
    )


def _fake_worklog(wl_id: str):
    return SimpleNamespace(
        id=wl_id, started_datetime=STARTED, created_datetime=None,
        timeSpentSeconds=3600, hours=1.0, comment_text=None, comment=None,
        author=SimpleNamespace(jira_account_id="acc-1", name="login-1", display_name="A", email=None),
    )


async def _nothing(*args, **kwargs):
    return
    yield  # pragma: no cover


async def test_bulk_reload_keeps_cloud_worklogs(db_session, world):
    jira = MagicMock()
    jira.get_worklogs_updated_since = _nothing
    jira.iter_deleted_worklog_ids = _nothing

    stats = await SyncService(db_session, jira).reload_worklogs_v2_bulk(date(2026, 1, 1))

    assert _remaining(db_session) == {"cloud:850609"}
    assert stats.deleted == 1


async def test_reload_by_date_keeps_cloud_worklogs(db_session, world):
    jira = MagicMock()
    jira.iter_issues = _nothing

    stats = await SyncService(db_session, jira).reload_worklogs_since(date(2026, 1, 1))

    assert _remaining(db_session) == {"cloud:850609"}
    assert stats.deleted == 1


async def test_issue_diff_keeps_cloud_worklogs(db_session, world):
    """Ведро A: ворклоги задачи, которых нет в Jira, удаляются — кроме облачных."""
    jira = MagicMock()

    async def issues(jql, **kwargs):
        if "worklogAuthor" not in jql:
            yield _fake_issue()

    async def worklogs(jira_issue_id):
        yield _fake_worklog("wl-1")

    jira.iter_issues = issues
    jira.iter_worklogs_for_issue = worklogs

    await SyncService(db_session, jira).update_worklogs_since(date(2026, 3, 1))

    assert _remaining(db_session) == {"cloud:850609", "wl-1"}


async def test_author_diff_keeps_cloud_worklogs(db_session, world):
    """Ведро B (по авторам команды): тот же разбор задачи — облачные не удаляются."""
    jira = MagicMock()

    async def issues(jql, **kwargs):
        if "worklogAuthor" in jql:
            yield _fake_issue()

    async def worklogs(jira_issue_id):
        yield _fake_worklog("wl-1")

    jira.iter_issues = issues
    jira.iter_worklogs_for_issue = worklogs

    stats = await SyncService(db_session, jira).update_worklogs_since(date(2026, 3, 1), teams=["Alpha"])

    assert _remaining(db_session) == {"cloud:850609", "wl-1"}
    assert stats.bucket_b_worklogs_deleted == 1
