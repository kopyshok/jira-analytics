"""Тесты reload_worklogs_v2_bulk — bulk Jira API path."""

from datetime import date, datetime, timezone

import pytest

from app.connectors.schemas import JiraWorklogAuthorSchema, JiraWorklogSchema
from app.models import Employee, Issue, Project, Worklog
from app.services.sync_service import SyncService, ReloadStats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _author(account_id: str = "a1") -> JiraWorklogAuthorSchema:
    return JiraWorklogAuthorSchema(
        accountId=account_id,
        displayName="Тест",
        emailAddress=f"{account_id}@example.com",
    )


def _worklog(wl_id: str, issue_id: str, started: str, account_id: str = "a1") -> JiraWorklogSchema:
    return JiraWorklogSchema(
        id=wl_id,
        issueId=issue_id,
        author=_author(account_id),
        started=started,
        timeSpentSeconds=3600,
        comment=None,
        created=started,
        updated=started,
    )


class MockJira:
    """Минимальный mock JiraClient для reload_worklogs_v2_bulk."""

    def __init__(self, worklogs: list[JiraWorklogSchema]):
        self._worklogs = worklogs

    async def get_worklogs_updated_since(self, since_dt: datetime):
        for wl in self._worklogs:
            yield wl

    async def iter_deleted_worklog_ids(self, since_dt: datetime):
        return
        yield  # pragma: no cover


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_data(db_session):
    """Один проект, один сотрудник, одна задача."""
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
    db_session.commit()
    return {"project": project, "employee": employee, "issue": issue}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_reload_v2_deletes_and_reinserts(db_session, base_data):
    """Удаляет 3 локальных ворклога, Jira возвращает 2 — итого 2 в БД."""
    issue = base_data["issue"]
    employee = base_data["employee"]
    since = date(2026, 1, 1)

    # Создать 3 локальных ворклога после since
    for i, wl_id in enumerate(["w1", "w2", "w3"]):
        db_session.add(Worklog(
            id=wl_id,
            jira_worklog_id=wl_id,
            issue_id=issue.id,
            employee_id=employee.id,
            started_at=datetime(2026, 1, 10 + i, 9, 0),
            hours=1.0,
            time_spent_seconds=3600,
        ))
    db_session.commit()

    # Jira знает только о w1 и w2 (w3 удалён в Jira)
    jira_worklogs = [
        _worklog("w1", "1001", "2026-01-10T09:00:00.000+0000"),
        _worklog("w2", "1001", "2026-01-11T09:00:00.000+0000"),
    ]
    service = SyncService(db_session, jira_client=MockJira(jira_worklogs))
    stats = await service.reload_worklogs_v2_bulk(since)

    assert isinstance(stats, ReloadStats)
    assert stats.deleted == 3
    assert stats.worklogs_inserted == 2

    remaining = {w.jira_worklog_id for w in db_session.query(Worklog).all()}
    assert remaining == {"w1", "w2"}


async def test_reload_v2_skips_unknown_issues(db_session, base_data):
    """Ворклог для issue, которой нет в БД, — пропускается."""
    since = date(2026, 1, 1)

    # Jira возвращает ворклог с неизвестным issueId
    jira_worklogs = [
        _worklog("w_unk", "9999", "2026-01-15T09:00:00.000+0000"),
    ]
    service = SyncService(db_session, jira_client=MockJira(jira_worklogs))
    stats = await service.reload_worklogs_v2_bulk(since)

    assert stats.deleted == 0
    assert stats.issues_scanned == 0
    assert stats.worklogs_inserted == 0
    assert db_session.query(Worklog).count() == 0


async def test_reload_v2_filters_started_before_since(db_session, base_data):
    """Ворклог с started_at до since — пропускается (исторический дрейф)."""
    since = date(2026, 1, 1)

    # Jira возвращает ворклог, started до since (Jira мог обновить его позже)
    jira_worklogs = [
        _worklog("w_old", "1001", "2025-12-20T09:00:00.000+0000"),
    ]
    service = SyncService(db_session, jira_client=MockJira(jira_worklogs))
    stats = await service.reload_worklogs_v2_bulk(since)

    assert stats.deleted == 0
    assert stats.worklogs_inserted == 0
    assert db_session.query(Worklog).count() == 0
