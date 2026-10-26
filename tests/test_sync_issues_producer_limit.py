"""Загрузка задач читает Jira DC не больше чем по ``ISSUE_PRODUCERS`` проектам сразу."""

import asyncio
from unittest.mock import MagicMock

from app.models import Project
from app.services import sync_service
from app.services.sync_service import SyncService


async def test_issue_producers_are_limited(db_session):
    keys = [f"P{n}" for n in range(7)]
    db_session.add_all(Project(jira_project_id=str(10000 + n), key=k, name=k) for n, k in enumerate(keys))
    db_session.commit()

    active = 0
    peak = 0
    seen: list[str] = []

    async def fake_iter_issues(jql, max_results, fields, expand=None):  # noqa: ARG001
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        seen.append(jql)
        await asyncio.sleep(0.01)
        active -= 1
        return
        yield  # pragma: no cover

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    await SyncService(db_session, jira).sync_issues(project_keys=keys, incremental=False)

    assert len(seen) == 7
    assert peak == sync_service.ISSUE_PRODUCERS == 3


async def test_failed_consumer_does_not_hang_on_full_queue(db_session):
    """Загрузка оборвалась, пока очередь задач полна: чтение Jira не ждёт места
    в очереди вечно (раньше метка конца ждала место, и синк висел до перезапуска)."""
    import pytest

    db_session.add(Project(jira_project_id="20000", key="FULL", name="FULL"))
    db_session.commit()

    async def endless_issues(jql, max_results, fields, expand=None):  # noqa: ARG001
        for _ in range(2000):
            yield MagicMock()

    async def cancel_after_queue_filled() -> bool:
        await asyncio.sleep(0.05)  # чтение успевает забить очередь до отказа
        return True

    jira = MagicMock()
    jira.iter_issues = endless_issues
    svc = SyncService(db_session, jira, cancel_check=cancel_after_queue_filled)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(svc.sync_issues(project_keys=["FULL"], incremental=False), timeout=5)
