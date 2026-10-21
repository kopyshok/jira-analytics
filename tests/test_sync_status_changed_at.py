"""«Статус изменён» и дни паузы в Jira DC считаются из истории изменений."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.connectors.jira_client import (
    JiraAuthError, JiraClientError, JiraNetworkError, JiraRateLimitError, JiraTimeoutError,
)
from app.connectors.schemas import JiraIssueSchema
from app.models import Issue, Project
from app.services.sync_service import SyncService
from tests.dc_fixtures import load_dc

CATEGORIES = {"1": "new", "3": "indeterminate", "10205": "indeterminate"}


def _dc_issue(name: str = "issue_OS-91030.json", changelog=None) -> JiraIssueSchema:
    raw = load_dc(name)
    if changelog is not None:
        raw["changelog"] = changelog
    return JiraIssueSchema.model_validate(raw)


def _project(db):
    db.add(Project(id="p-os", jira_project_id="10901", key="OS", name="1С"))
    db.commit()


def test_status_changed_at_is_last_category_change(db_session):
    _project(db_session)
    svc = SyncService(db_session, MagicMock())
    svc._status_categories = CATEGORIES
    changelog = {"total": 2, "histories": [
        {"created": "2026-09-12T08:00:00.000+0000",
         "items": [{"field": "status", "from": "1", "to": "3"}]},
        {"created": "2026-09-20T10:00:00.000+0000",
         "items": [{"field": "status", "from": "3", "to": "10205"}]},
    ]}
    issue, _ = svc._upsert_issue(_dc_issue(changelog=changelog), "p-os")
    assert issue.status_changed_at == datetime(2026, 9, 12, 8, 0)


def test_status_changed_at_falls_back_to_created(db_session):
    _project(db_session)
    svc = SyncService(db_session, MagicMock())
    svc._status_categories = CATEGORIES
    issue, _ = svc._upsert_issue(_dc_issue(changelog={"total": 0, "histories": []}), "p-os")
    assert issue.status_changed_at is not None
    assert issue.status_changed_at == issue.jira_created_at


async def test_ensure_status_categories_builds_map(db_session):
    jira = MagicMock()
    jira.get_statuses = AsyncMock(return_value=[
        {"id": "1", "name": "Открыт", "statusCategory": {"key": "new"}},
        {"id": "3", "name": "В работе", "statusCategory": {"key": "indeterminate"}},
    ])
    svc = SyncService(db_session, jira)
    await svc._ensure_status_categories()
    await svc._ensure_status_categories()
    assert svc._status_categories == {"1": "new", "3": "indeterminate"}
    jira.get_statuses.assert_awaited_once()


async def test_ensure_status_categories_survives_failure(db_session):
    jira = MagicMock()
    jira.get_statuses = AsyncMock(side_effect=RuntimeError("нет связи"))
    svc = SyncService(db_session, jira)
    await svc._ensure_status_categories()
    assert svc._status_categories == {}


async def test_truncated_changelog_is_fetched_in_full(db_session):
    status = {"field": "status", "from": "1", "to": "3", "toString": "В работе"}
    full = {"total": 2, "histories": [
        {"id": "1", "created": "a", "items": [status, {"field": "assignee", "to": "x"}]},
        {"id": "2", "created": "b", "items": []},
    ]}
    jira = MagicMock()
    jira.get_issue_changelog = AsyncMock(return_value=full)
    svc = SyncService(db_session, jira)

    issue = _dc_issue(changelog={"total": 2, "histories": [{"created": "a", "items": []}]})
    await svc._complete_changelog(issue)
    # В памяти — только смены статуса.
    assert issue.changelog == {"total": 2, "histories": [
        {"created": "a", "items": [status]}, {"created": "b", "items": []},
    ]}

    await svc._complete_changelog(issue)
    await svc._complete_changelog(_dc_issue())
    jira.get_issue_changelog.assert_awaited_once_with("OS-91030")


async def test_sync_issues_requests_changelog(db_session):
    _project(db_session)
    expands: list = []

    async def fake_iter_issues(jql, max_results, fields, expand=None):
        expands.append(expand)
        yield _dc_issue()

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    jira.get_fields = AsyncMock(return_value=[])
    jira.get_statuses = AsyncMock(return_value=[
        {"id": "10205", "statusCategory": {"key": "indeterminate"}},
    ])
    svc = SyncService(db_session, jira)
    await svc.sync_issues(project_keys=["OS"], incremental=False)
    assert expands == ["changelog"]
    assert svc._status_categories == {"10205": "indeterminate"}
    issue = db_session.query(Issue).filter_by(key="OS-91030").one()
    assert issue.status_changed_at is not None
    assert issue.status_changed_at == issue.jira_created_at


async def test_search_changelog_keeps_only_status_items(db_session):
    _project(db_session)
    status = {"field": "status", "from": "1", "to": "3", "toString": "В работе"}
    found = _dc_issue(changelog={"total": 1, "histories": [
        {"id": "1", "created": "2026-09-12T08:00:00.000+0000", "author": {"key": "U1"},
         "items": [{"field": "assignee", "to": "x"}, status]},
    ]})

    async def fake_iter_issues(jql, max_results, fields, expand=None):
        yield found

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    jira.get_fields = AsyncMock(return_value=[])
    jira.get_statuses = AsyncMock(return_value=[])
    await SyncService(db_session, jira).sync_issues(project_keys=["OS"], incremental=False)
    assert found.changelog == {"total": 1, "histories": [
        {"created": "2026-09-12T08:00:00.000+0000", "items": [status]},
    ]}


async def test_missing_full_history_keeps_stored_values(db_session, caplog):
    _project(db_session)
    stored = datetime(2026, 1, 15, 10, 0)
    db_session.add(Issue(id="i1", jira_issue_id="258783", key="OS-91030", summary="s",
                         issue_type="Задача", status="В работе", project_id="p-os",
                         status_changed_at=stored, paused_days=5.0))
    db_session.commit()
    truncated = {"total": 3, "histories": [
        {"created": "2026-09-01T09:00:00.000+0000",
         "items": [{"field": "status", "from": "3", "to": "9", "toString": "Приостановлено"}]},
    ]}

    async def fake_iter_issues(jql, max_results=100, fields=None, expand=None, lenient=False):
        yield _dc_issue(changelog=truncated)

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    jira.get_fields = AsyncMock(return_value=[])
    jira.get_statuses = AsyncMock(return_value=[])
    jira.get_issue_changelog = AsyncMock(return_value={})
    svc = SyncService(db_session, jira)

    assert await svc.refresh_issues_by_keys(["OS-91030"]) == (1, 1)
    assert await svc.sync_paused_days(project_keys=["OS"], incremental=False) == 0

    issue = db_session.get(Issue, "i1")
    assert issue.status_changed_at == stored
    assert issue.paused_days == 5.0
    assert "OS-91030" in caplog.text


async def test_paused_days_read_from_search_changelog(db_session):
    _project(db_session)
    db_session.add(Issue(id="i1", jira_issue_id="258783", key="OS-91030", summary="s",
                         issue_type="Задача", status="В работе", project_id="p-os"))
    db_session.commit()
    changelog = {"total": 2, "histories": [
        {"created": "2026-09-01T09:00:00.000+0000",
         "items": [{"field": "status", "from": "3", "to": "9", "toString": "Приостановлено"}]},
        {"created": "2026-09-04T09:00:00.000+0000",
         "items": [{"field": "status", "from": "9", "to": "3", "toString": "В работе"}]},
    ]}
    expands: list = []
    lenients: list = []

    async def fake_iter_issues(jql, max_results=100, fields=None, expand=None, lenient=False):
        expands.append(expand)
        lenients.append(lenient)
        yield _dc_issue(changelog=changelog)

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    jira.get_status_changes = AsyncMock()
    jira.get_issue_changelog = AsyncMock()
    svc = SyncService(db_session, jira)

    updated = await svc.sync_paused_days(project_keys=["OS"], incremental=False)

    assert updated == 1
    assert expands == ["changelog"]
    assert lenients == [True]  # нет статуса паузы в Jira — не ошибка поиска
    assert db_session.get(Issue, "i1").paused_days == 3.0
    jira.get_status_changes.assert_not_called()
    jira.get_issue_changelog.assert_not_called()


def test_new_issue_with_incomplete_history_gets_created_date(db_session):
    """Новая задача, историю дочитать не удалось: опоры нет — дата создания, а не пусто."""
    _project(db_session)
    svc = SyncService(db_session, MagicMock())
    svc._status_categories = CATEGORIES
    truncated = {"total": 3, "histories": [
        {"created": "2026-09-12T08:00:00.000+0000",
         "items": [{"field": "status", "from": "1", "to": "3"}]},
    ]}
    issue, created = svc._upsert_issue(_dc_issue(changelog=truncated), "p-os")
    assert created
    assert issue.status_changed_at is not None
    assert issue.status_changed_at == issue.jira_created_at


async def test_changelog_fetch_failure_skips_only_that_issue(db_session, caplog):
    """История одной задачи не читается (404) — остальные задачи этапа обрабатываются."""
    _project(db_session)
    stored = datetime(2026, 1, 15, 10, 0)
    db_session.add_all([
        Issue(id="i1", jira_issue_id="258783", key="OS-91030", summary="s",
              issue_type="Задача", status="В работе", project_id="p-os",
              status_changed_at=stored, paused_days=5.0),
        Issue(id="i2", jira_issue_id="258784", key="OS-91031", summary="s",
              issue_type="Задача", status="В работе", project_id="p-os"),
    ])
    db_session.commit()
    truncated = {"total": 3, "histories": [
        {"created": "2026-09-01T09:00:00.000+0000",
         "items": [{"field": "status", "from": "3", "to": "9", "toString": "Приостановлено"}]},
    ]}
    complete = {"total": 2, "histories": [
        {"created": "2026-09-01T09:00:00.000+0000",
         "items": [{"field": "status", "from": "3", "to": "9", "toString": "Приостановлено"}]},
        {"created": "2026-09-04T09:00:00.000+0000",
         "items": [{"field": "status", "from": "9", "to": "3", "toString": "В работе"}]},
    ]}

    async def fake_iter_issues(jql, max_results=100, fields=None, expand=None, lenient=False):
        yield _dc_issue(changelog=truncated)
        yield _dc_issue("issue_OS-91031.json", changelog=complete)

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    jira.get_fields = AsyncMock(return_value=[])
    jira.get_statuses = AsyncMock(return_value=[])
    jira.get_issue_changelog = AsyncMock(side_effect=JiraClientError("404 Issue Does Not Exist"))
    svc = SyncService(db_session, jira)

    assert await svc.refresh_issues_by_keys(["OS-91030", "OS-91031"]) == (2, 2)
    assert await svc.sync_paused_days(project_keys=["OS"], incremental=False) == 1

    first = db_session.get(Issue, "i1")
    assert first.status_changed_at == stored
    assert first.paused_days == 5.0
    second = db_session.get(Issue, "i2")
    assert second.paused_days == 3.0
    assert second.status_changed_at is not None
    assert "OS-91030" in caplog.text


@pytest.mark.parametrize("error", [
    JiraAuthError("Access forbidden. Check permissions."),
    JiraRateLimitError(60),
    JiraNetworkError("Request failed: нет связи"),
])
async def test_changelog_fetch_systemic_failure_stops_stage(db_session, error):
    """Нет доступа, лимит запросов, нет сети — это сбой всего этапа, а не одной задачи."""
    jira = MagicMock()
    jira.get_issue_changelog = AsyncMock(side_effect=error)
    svc = SyncService(db_session, jira)
    truncated = {"total": 3, "histories": [{"created": "a", "items": []}]}

    with pytest.raises(type(error)):
        await svc._complete_changelog(_dc_issue(changelog=truncated))


async def test_changelog_fetch_not_found_is_skipped(db_session, caplog):
    """Задачи уже нет (404) — предупреждение, обрывок истории остаётся."""
    jira = MagicMock()
    jira.get_issue_changelog = AsyncMock(side_effect=JiraClientError("404 Issue Does Not Exist"))
    svc = SyncService(db_session, jira)
    issue = _dc_issue(changelog={"total": 3, "histories": [{"created": "a", "items": []}]})

    await svc._complete_changelog(issue)

    assert issue.changelog["total"] == 3
    assert "OS-91030" in caplog.text


async def test_changelog_fetch_timeout_is_skipped(db_session, caplog):
    """История одной задачи не пришла вовремя (огромная история) — этап идёт дальше."""
    jira = MagicMock()
    jira.get_issue_changelog = AsyncMock(side_effect=JiraTimeoutError("Request failed: ReadTimeout"))
    svc = SyncService(db_session, jira)
    issue = _dc_issue(changelog={"total": 3, "histories": [{"created": "a", "items": []}]})

    await svc._complete_changelog(issue)

    assert issue.changelog["total"] == 3
    assert "OS-91030" in caplog.text
