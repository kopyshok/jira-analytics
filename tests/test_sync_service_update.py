"""Tests for SyncService.update_worklogs_since (upsert-only)."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Employee, Issue, Project, Worklog
from app.services.sync_service import SyncService


@pytest.fixture
def project(db_session):
    p = Project(
        id="p-1", jira_project_id="10000", key="PRJ",
        name="Test",
        synced_at=datetime.utcnow(),
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def issue(db_session, project):
    i = Issue(
        id="i-1", jira_issue_id="20000", key="PRJ-1",
        project_id=project.id, summary="s", issue_type="Task",
        status="Open", status_category="new",
        synced_at=datetime.utcnow(),
    )
    db_session.add(i)
    db_session.commit()
    return i


def _fake_issue(jira_id: str, key: str):
    return SimpleNamespace(
        id=jira_id, key=key,
        fields=SimpleNamespace(
            summary="s",
            issuetype=SimpleNamespace(name="Task"),
            status=SimpleNamespace(
                name="Open",
                statusCategory=SimpleNamespace(key="new"),
            ),
            project=SimpleNamespace(id="10000", key="PRJ", name="Test"),
        ),
    )


def _fake_worklog(wl_id: str, started_iso: str, author_id="acc-1", seconds=3600):
    started_dt = datetime.fromisoformat(started_iso)
    return SimpleNamespace(
        id=wl_id,
        started_datetime=started_dt,
        timeSpentSeconds=seconds,
        hours=seconds / 3600,
        comment_text=None,
        author=SimpleNamespace(
            accountId=author_id,
            displayName="Author",
            emailAddress=None,
        ),
        comment=None,
    )


@pytest.mark.asyncio
async def test_update_does_not_delete_existing(db_session, issue):
    """Reload удаляет worklogs; update — нет."""
    pre = Worklog(
        id="w-old", jira_worklog_id="old-1",
        issue_id=issue.id, employee_id=None,
        started_at=datetime(2026, 1, 1),
        hours=1.0, time_spent_seconds=3600,
        synced_at=datetime.utcnow(),
    )
    emp = Employee(
        id="e-1", jira_account_id="acc-1", display_name="A",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add_all([emp, pre])
    pre.employee_id = emp.id
    db_session.commit()

    jira = MagicMock()

    async def fake_iter_issues(jql, fields=None, max_results=100):
        if False:
            yield
        return
    jira.iter_issues = fake_iter_issues

    svc = SyncService(db_session, jira)
    stats = await svc.update_worklogs_since(date(2026, 2, 1))
    assert stats.deleted == 0
    assert db_session.query(Worklog).filter_by(id="w-old").one() is not None


@pytest.mark.asyncio
async def test_update_catches_back_dated_via_updated_jql(db_session, issue):
    """issue.updated = сегодня, worklog.started в прошлом < since — ловим."""
    captured_jqls: list[str] = []
    jira = MagicMock()

    async def fake_iter_issues(jql, fields=None, max_results=100):
        captured_jqls.append(jql)
        yield _fake_issue("20000", "PRJ-1")
    jira.iter_issues = fake_iter_issues

    async def fake_iter_worklogs_for_issue(jira_issue_id):
        yield _fake_worklog("wl-backdated", "2026-01-20T10:00:00")
    jira.iter_worklogs_for_issue = fake_iter_worklogs_for_issue

    svc = SyncService(db_session, jira)
    stats = await svc.update_worklogs_since(date(2026, 2, 1))
    assert any("updated" in q for q in captured_jqls)
    assert stats.worklogs_upserted == 1
    wl = db_session.query(Worklog).filter_by(jira_worklog_id="wl-backdated").one()
    assert wl.started_at == datetime(2026, 1, 20, 10, 0, 0)


@pytest.mark.asyncio
async def test_update_upserts_changed_started_at(db_session, issue):
    """Повторный upsert с изменённым started_at обновляет запись, не плодит дубль."""
    emp = Employee(
        id="e-1", jira_account_id="acc-1", display_name="A",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.add(Worklog(
        id="w-1", jira_worklog_id="wl-1",
        issue_id=issue.id, employee_id=emp.id,
        started_at=datetime(2026, 2, 5, 10),
        hours=1.0, time_spent_seconds=3600,
        synced_at=datetime.utcnow(),
    ))
    db_session.commit()

    jira = MagicMock()

    async def fake_iter_issues(jql, fields=None, max_results=100):
        yield _fake_issue("20000", "PRJ-1")
    jira.iter_issues = fake_iter_issues

    async def fake_iter_worklogs_for_issue(jira_issue_id):
        yield _fake_worklog("wl-1", "2026-02-05T14:00:00")  # новый started
    jira.iter_worklogs_for_issue = fake_iter_worklogs_for_issue

    svc = SyncService(db_session, jira)
    await svc.update_worklogs_since(date(2026, 2, 1))

    wls = db_session.query(Worklog).filter_by(jira_worklog_id="wl-1").all()
    assert len(wls) == 1
    assert wls[0].started_at == datetime(2026, 2, 5, 14, 0, 0)


@pytest.mark.asyncio
async def test_bucket_b_creates_out_of_scope_issue(db_session):
    """Ворклог сотрудника команды на чужой задаче → создаётся Issue(out_of_scope=True)."""
    from app.models import EmployeeTeam

    emp = Employee(
        id="e-1", jira_account_id="acc-1", display_name="A",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id="et-1", employee_id="e-1", team="Alpha", is_primary=True,
    ))
    db_session.commit()

    jira = MagicMock()
    a_calls: list[str] = []
    b_calls: list[str] = []

    async def fake_iter_issues(jql, fields=None, max_results=100):
        if "worklogAuthor" in jql:
            b_calls.append(jql)
            yield _fake_issue("30000", "OTHER-1")
        else:
            a_calls.append(jql)
            if False:
                yield

    async def fake_iter_worklogs_for_issue(jira_issue_id):
        yield _fake_worklog("wl-b", "2026-02-10T10:00:00", author_id="acc-1")

    jira.iter_issues = fake_iter_issues
    jira.iter_worklogs_for_issue = fake_iter_worklogs_for_issue

    svc = SyncService(db_session, jira)
    stats = await svc.update_worklogs_since(date(2026, 2, 1), teams=["Alpha"])

    assert stats.bucket_b_out_of_scope_created == 1
    assert stats.bucket_b_worklogs_upserted == 1
    created = db_session.query(Issue).filter_by(jira_issue_id="30000").one()
    assert created.out_of_scope is True
    assert created.key == "OTHER-1"
    assert created.project_id is not None


@pytest.mark.asyncio
async def test_bucket_b_does_not_clobber_in_scope(db_session, issue):
    """Existing in-scope issue (out_of_scope=False) остаётся in-scope даже если
    Ведро B находит по ней ворклоги нашего сотрудника."""
    from app.models import EmployeeTeam

    emp = Employee(
        id="e-1", jira_account_id="acc-1", display_name="A",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id="et-1", employee_id="e-1", team="Alpha", is_primary=True,
    ))
    db_session.commit()

    jira = MagicMock()

    async def fake_iter_issues(jql, fields=None, max_results=100):
        if "worklogAuthor" in jql:
            yield _fake_issue("20000", "PRJ-1")  # EXISTS in DB as in-scope
        else:
            if False:
                yield

    async def fake_iter_worklogs_for_issue(jira_issue_id):
        yield _fake_worklog("wl-b", "2026-02-10T10:00:00", author_id="acc-1")

    jira.iter_issues = fake_iter_issues
    jira.iter_worklogs_for_issue = fake_iter_worklogs_for_issue

    svc = SyncService(db_session, jira)
    await svc.update_worklogs_since(date(2026, 2, 1), teams=["Alpha"])

    db_session.refresh(issue)
    assert issue.out_of_scope is False


@pytest.mark.asyncio
async def test_bucket_b_skips_when_team_has_no_employees(db_session):
    """Если в ``employee_teams`` нет записей для заданной команды — пропускаем."""
    jira = MagicMock()
    calls: list[str] = []

    async def fake_iter_issues(jql, fields=None, max_results=100):
        calls.append(jql)
        if False:
            yield

    jira.iter_issues = fake_iter_issues

    svc = SyncService(db_session, jira)
    await svc.update_worklogs_since(date(2026, 2, 1), teams=["NonexistentTeam"])
    # Only Bucket A JQL fired, no Bucket B
    assert all("worklogAuthor" not in q for q in calls)
