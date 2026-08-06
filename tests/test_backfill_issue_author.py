"""Разовое дозаполнение «автора задачи»: подменяет робота на Автора из Jira."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.jobs.backfill_issue_author import (
    FLAG_KEY, RUNNING_PREFIX, backfill_issue_author_once,
)
from app.models.app_setting import AppSetting
from app.models.issue import Issue
from app.models.project import Project


class _StubJira:
    """Клиент Jira, отдающий одну задачу с живым Автором вместо робота."""

    def __init__(self):
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def iter_issues(self, jql, max_results=100, fields=None):
        self.calls += 1
        yield SimpleNamespace(
            key="OS-1",
            fields=SimpleNamespace(
                reporter=SimpleNamespace(jira_account_id="acc-human",
                                         display_name="Копышков Николай"),
                creator=SimpleNamespace(jira_account_id="acc-bot",
                                        display_name="Automation for Jira"),
            ),
        )


def test_backfill_replaces_bot_author_and_runs_once(db_session):
    db_session.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    db_session.add(Issue(
        id="i1", jira_issue_id="10001", key="OS-1", summary="Тест",
        issue_type="Задача", status="ГОТОВО", project_id="p1",
        reporter_account_id="acc-bot", reporter_display_name="Automation for Jira",
    ))
    db_session.commit()

    factory = lambda: db_session  # noqa: E731 — сессия теста вместо своей
    jira = _StubJira()

    changed = asyncio.run(backfill_issue_author_once(client=jira, _session_factory=factory))
    assert changed == 1
    row = db_session.query(Issue).filter_by(key="OS-1").one()
    assert row.reporter_account_id == "acc-human"
    assert row.reporter_display_name == "Копышков Николай"
    assert db_session.query(AppSetting).filter_by(key=FLAG_KEY).one().value != "running"

    # Повторный запуск (перезапуск сервиса) ничего не делает — Jira не читается.
    again = asyncio.run(backfill_issue_author_once(client=jira, _session_factory=factory))
    assert again == 0
    assert jira.calls == 1


def test_backfill_retries_after_interrupted_run(db_session):
    """Сервис перезапустили посреди пересчёта — следующий запуск доделывает."""
    db_session.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    db_session.add(Issue(
        id="i1", jira_issue_id="10001", key="OS-1", summary="Тест",
        issue_type="Задача", status="ГОТОВО", project_id="p1",
        reporter_account_id="acc-bot", reporter_display_name="Automation for Jira",
    ))
    stale = (datetime.utcnow() - timedelta(hours=2)).isoformat(timespec="seconds")
    db_session.add(AppSetting(id="s1", key=FLAG_KEY, value=RUNNING_PREFIX + stale))
    db_session.commit()

    factory = lambda: db_session  # noqa: E731
    changed = asyncio.run(backfill_issue_author_once(client=_StubJira(), _session_factory=factory))
    assert changed == 1
