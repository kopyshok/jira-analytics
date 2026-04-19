"""Тесты отмены синхронизации по коллбеку cancel_check.

Проверяем, что SyncService корректно поднимает CancelledError, когда
cancel_check возвращает True, и делает это *между* обработкой элементов
в горячих циклах (проекты, issues, worklogs, comments).
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Issue, Project
from app.services.sync_service import SyncService


def _make_project_schema(jid: str, key: str):
    """Мин. схема проекта для iter_projects (поля согласно JiraProjectSchema)."""
    from app.connectors.schemas import JiraProjectSchema

    return JiraProjectSchema(id=jid, key=key, name=f"Project {key}")


class _AsyncGen:
    """Простейший async-итератор по списку элементов, считающий переданное."""

    def __init__(self, items):
        self._items = list(items)
        self.consumed = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        self.consumed += 1
        return self._items.pop(0)


@pytest.mark.asyncio
async def test_sync_projects_cancels_between_items(db_session):
    """Если cancel_check возвращает True перед первым проектом — падает сразу."""
    projects = [_make_project_schema(str(i), f"P{i}") for i in range(5)]
    gen = _AsyncGen(projects)

    jira = MagicMock()
    jira.iter_projects = MagicMock(return_value=gen)

    # cancel_check сразу возвращает True.
    cancel = AsyncMock(return_value=True)
    svc = SyncService(db_session, jira, cancel_check=cancel)

    with pytest.raises(asyncio.CancelledError):
        await svc.sync_projects()

    # Хотя бы один элемент должен был быть прочитан из генератора
    # (check стоит внутри цикла, после yield'а первого проекта).
    assert gen.consumed == 1
    assert cancel.await_count >= 1


@pytest.mark.asyncio
async def test_sync_projects_runs_when_not_cancelled(db_session):
    """Без отмены sync_projects проходит все проекты без ошибок."""
    projects = [_make_project_schema(str(i), f"P{i}") for i in range(3)]
    gen = _AsyncGen(projects)

    jira = MagicMock()
    jira.iter_projects = MagicMock(return_value=gen)

    cancel = AsyncMock(return_value=False)
    svc = SyncService(db_session, jira, cancel_check=cancel)

    count = await svc.sync_projects()
    assert count == 3
    # check вызывался перед каждой обработкой проекта
    assert cancel.await_count == 3


@pytest.mark.asyncio
async def test_sync_worklogs_checks_cancel_per_issue(db_session):
    """Перед обработкой каждой issue (во внешнем for) делается cancel-check."""
    # Есть 2 локальных issue — проверяем, что cancel-check вызывается для
    # обеих (или до первой, если немедленная отмена).
    proj = Project(id="p1", jira_project_id="10", key="PRJ", name="P")
    db_session.add(proj)
    issues = []
    for i in range(3):
        iss = Issue(
            id=f"i{i}", jira_issue_id=str(100 + i), key=f"PRJ-{i}",
            summary="x", project_id="p1", issue_type="Task", status="В работе",
        )
        db_session.add(iss)
        issues.append(iss)
    db_session.commit()

    # Первый вызов — False, второй — True → отмена перед 2-й issue.
    cancel = AsyncMock(side_effect=[False, True])
    jira = MagicMock()
    # Для первой issue — пустой генератор ворклогов.
    jira.iter_worklogs_for_issue = MagicMock(return_value=_AsyncGen([]))
    svc = SyncService(db_session, jira, cancel_check=cancel)

    with pytest.raises(asyncio.CancelledError):
        await svc.sync_worklogs()

    # Две проверки: одна прошла (False), вторая подняла CancelledError.
    assert cancel.await_count == 2
