"""Tests for SyncService.update_worklogs_v2 (bulk worklog API)."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

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


def _fake_worklog_schema(wl_id: str, issue_id: str, started_iso: str,
                          author_id: str = "acc-1", seconds: int = 3600):
    """SimpleNamespace имитирующий JiraWorklogSchema."""
    started_dt = datetime.fromisoformat(started_iso)
    return SimpleNamespace(
        id=wl_id,
        issueId=issue_id,
        started=started_iso,
        started_datetime=started_dt,
        timeSpentSeconds=seconds,
        hours=seconds / 3600,
        comment_text=None,
        comment=None,
        author=SimpleNamespace(
            accountId=author_id,
            displayName="Author",
            emailAddress=None,
        ),
    )


@pytest.mark.asyncio
async def test_update_v2_upserts_from_bulk_api(db_session, issue):
    """update_worklogs_v2 upsert'ит ворклоги пришедшие из bulk API."""
    wl1 = _fake_worklog_schema("wl-1", "20000", "2026-04-01T10:00:00")
    wl2 = _fake_worklog_schema("wl-2", "20000", "2026-04-02T11:00:00")

    jira = MagicMock()

    async def fake_bulk(since):
        yield wl1
        yield wl2

    async def fake_deleted(since):
        return
        yield  # noqa: unreachable — делает функцию async generator

    jira.get_worklogs_updated_since = fake_bulk
    jira.iter_deleted_worklog_ids = fake_deleted

    svc = SyncService(db_session, jira)
    stats = await svc.update_worklogs_v2(date(2026, 4, 1))

    assert stats.bucket_a_worklogs_upserted == 2
    wls = db_session.query(Worklog).all()
    assert len(wls) == 2
    wl_ids = {w.jira_worklog_id for w in wls}
    assert wl_ids == {"wl-1", "wl-2"}


@pytest.mark.asyncio
async def test_update_v2_skips_unknown_issue(db_session):
    """Ворклог с issueId которого нет в БД — не создаётся."""
    wl = _fake_worklog_schema("wl-x", "99999", "2026-04-01T10:00:00")

    jira = MagicMock()

    async def fake_bulk(since):
        yield wl

    async def fake_deleted(since):
        return
        yield  # noqa: unreachable — делает функцию async generator

    jira.get_worklogs_updated_since = fake_bulk
    jira.iter_deleted_worklog_ids = fake_deleted

    svc = SyncService(db_session, jira)
    stats = await svc.update_worklogs_v2(date(2026, 4, 1))

    assert stats.bucket_a_worklogs_upserted == 0
    assert db_session.query(Worklog).count() == 0


@pytest.mark.asyncio
async def test_update_v2_handles_deleted_worklogs(db_session, issue):
    """Ворклоги удалённые в Jira удаляются из локальной БД через /worklog/deleted API."""
    wl1 = _fake_worklog_schema("wl-1", "20000", "2026-04-01T10:00:00")

    # Предварительно добавляем stale ворклог в БД (будет удалён через /worklog/deleted)
    emp = Employee(
        id="e-1", jira_account_id="acc-1", display_name="A",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    stale = Worklog(
        id="w-stale", jira_worklog_id="99999",
        issue_id=issue.id, employee_id=emp.id,
        started_at=datetime(2026, 3, 1),
        hours=1.0, time_spent_seconds=3600,
        synced_at=datetime.utcnow(),
    )
    db_session.add(stale)
    db_session.commit()

    jira = MagicMock()

    async def fake_bulk(since):
        yield wl1

    async def fake_deleted(since):
        yield 99999  # ID удалённого ворклога

    jira.get_worklogs_updated_since = fake_bulk
    jira.iter_deleted_worklog_ids = fake_deleted

    svc = SyncService(db_session, jira)
    stats = await svc.update_worklogs_v2(date(2026, 4, 1))

    # Stale ворклог удалён через /worklog/deleted
    assert stats.bucket_a_worklogs_deleted == 1
    assert db_session.query(Worklog).filter_by(jira_worklog_id="99999").count() == 0
    # wl-1 остался
    assert db_session.query(Worklog).filter_by(jira_worklog_id="wl-1").count() == 1
