"""Tests for per-issue worklog delete diff in update_worklogs_since."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Employee, Issue, Project, Worklog
from app.services.sync_service import SyncService


# ──────────────────────── fixtures ────────────────────────

@pytest.fixture
def project(db_session):
    p = Project(
        id="p-1", jira_project_id="10000", key="PRJ",
        name="Test", synced_at=datetime.utcnow(),
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


@pytest.fixture
def employee(db_session):
    emp = Employee(
        id="e-1", jira_account_id="acc-1", display_name="A",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.commit()
    return emp


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


def _fake_worklog(wl_id: str, author_id: str = "acc-1"):
    return SimpleNamespace(
        id=wl_id,
        started_datetime=datetime(2026, 3, 1, 10),
        timeSpentSeconds=3600,
        hours=1.0,
        comment_text=None,
        comment=None,
        author=SimpleNamespace(
            accountId=author_id,
            displayName="Author",
            emailAddress=None,
        ),
    )


def _add_worklog(db_session, wl_id: str, issue_id: str, employee_id: str) -> Worklog:
    wl = Worklog(
        id=wl_id,
        jira_worklog_id=wl_id,
        issue_id=issue_id,
        employee_id=employee_id,
        started_at=datetime(2026, 3, 1, 10),
        hours=1.0,
        time_spent_seconds=3600,
        synced_at=datetime.utcnow(),
    )
    db_session.add(wl)
    db_session.commit()
    return wl


# ──────────────────────── Bucket A delete diff ────────────────────────

@pytest.mark.asyncio
async def test_update_worklogs_deletes_stale_for_touched_issue(db_session, issue, employee):
    """Jira возвращает 2 ворклога; в БД 3 (один лишний) → после update остаётся 2."""
    _add_worklog(db_session, "wl-1", issue.id, employee.id)
    _add_worklog(db_session, "wl-2", issue.id, employee.id)
    _add_worklog(db_session, "wl-stale", issue.id, employee.id)  # будет удалён

    jira = MagicMock()

    async def fake_iter_issues(jql, fields=None, max_results=100):
        yield _fake_issue("20000", "PRJ-1")

    async def fake_iter_worklogs(jira_issue_id):
        yield _fake_worklog("wl-1")
        yield _fake_worklog("wl-2")

    jira.iter_issues = fake_iter_issues
    jira.iter_worklogs_for_issue = fake_iter_worklogs

    svc = SyncService(db_session, jira)
    stats = await svc.update_worklogs_since(date(2026, 3, 1))

    remaining = db_session.query(Worklog).filter_by(issue_id=issue.id).all()
    assert len(remaining) == 2
    ids = {w.jira_worklog_id for w in remaining}
    assert "wl-stale" not in ids
    assert stats.bucket_a_worklogs_deleted == 1
    assert stats.worklogs_deleted == 1
    assert stats.deleted == 1


@pytest.mark.asyncio
async def test_update_worklogs_no_delete_when_jira_empty_for_issue(db_session, issue, employee):
    """Если Jira возвращает 0 ворклогов для задачи — delete diff не запускается
    (jira_wl_ids пуст → условие if jira_wl_ids не выполняется)."""
    _add_worklog(db_session, "wl-keep", issue.id, employee.id)

    jira = MagicMock()

    async def fake_iter_issues(jql, fields=None, max_results=100):
        yield _fake_issue("20000", "PRJ-1")

    async def fake_iter_worklogs(jira_issue_id):
        if False:
            yield

    jira.iter_issues = fake_iter_issues
    jira.iter_worklogs_for_issue = fake_iter_worklogs

    svc = SyncService(db_session, jira)
    stats = await svc.update_worklogs_since(date(2026, 3, 1))

    # Нет ворклогов из Jira → diff не делаем, локальный остаётся
    remaining = db_session.query(Worklog).filter_by(issue_id=issue.id).all()
    assert len(remaining) == 1
    assert stats.bucket_a_worklogs_deleted == 0


@pytest.mark.asyncio
async def test_update_worklogs_no_delete_for_untouched_issue(db_session, issue, employee):
    """Если issue не пришла из Jira вообще — локальные ворклоги не трогаются."""
    _add_worklog(db_session, "wl-orphan", issue.id, employee.id)

    jira = MagicMock()

    async def fake_iter_issues(jql, fields=None, max_results=100):
        if False:
            yield

    jira.iter_issues = fake_iter_issues

    svc = SyncService(db_session, jira)
    stats = await svc.update_worklogs_since(date(2026, 3, 1))

    remaining = db_session.query(Worklog).filter_by(issue_id=issue.id).all()
    assert len(remaining) == 1
    assert stats.bucket_a_worklogs_deleted == 0
