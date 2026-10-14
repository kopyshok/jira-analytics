"""Проверка возможностей новой Jira: каждый нужный синку запрос вызван хотя бы раз."""
from datetime import datetime, timezone
from unittest.mock import patch

from app.models import AppSetting
from app.services.jira_migration.probe import essential_failures, run_probe
from tests.services.jira_migration.fake_jira import FakeJira, dc_user, dc_worklog

NOW = datetime(2026, 10, 14, 12, 0)
WORKLOG = dc_worklog("1", "258783", dc_user("JIRAUSER5", "Ivanov_I", "Иванов Иван"),
                     "2026-10-10T07:00:00.000+0000", 3600)


async def _probe(db, jira, team_field_id="customfield_11092"):
    jira.projects.setdefault("OS", "10901")  # образец проверки — из проекта, который есть в новой Jira
    return await run_probe(db, jira, sample_project="OS", sample_issue_key="OS-1",
                           team_field_id=team_field_id, now=NOW)


async def test_all_checks_pass(db_session):
    jira = FakeJira(worklogs=[WORKLOG])
    results = await _probe(db_session, jira)

    assert [r.code for r in results] == [
        "myself", "projects", "search", "fields", "statuses", "worklogs",
        "changelog", "editmeta", "team_options", "users",
    ]
    assert all(r.ok for r in results)
    assert essential_failures(results) == []
    since_ms = int(datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
    assert ("iter_worklogs_updated_since", since_ms) in jira.calls
    assert ("get_issue_changelog", "OS-1") in jira.calls
    assert ("get_editable_field_ids", "OS-1") in jira.calls
    assert ("search_users", "admin_login") in jira.calls


async def test_essential_failure_is_listed(db_session):
    results = await _probe(db_session, FakeJira(worklogs=[WORKLOG], fail={"get_fields"}))
    failed = essential_failures(results)
    assert [r.code for r in failed] == ["fields"]
    assert "сервер недоступен" in failed[0].detail


async def test_optional_failures_do_not_block(db_session):
    results = await _probe(
        db_session,
        FakeJira(worklogs=[WORKLOG], fail={"get_statuses", "search_users", "get_editable_field_ids"}),
    )
    assert essential_failures(results) == []
    assert {r.code for r in results if not r.ok} == {"statuses", "users", "editmeta"}


async def test_empty_editmeta_is_warning(db_session):
    results = await _probe(db_session, FakeJira(worklogs=[WORKLOG], editable_fields=set()))
    editmeta = next(r for r in results if r.code == "editmeta")
    assert (editmeta.ok, editmeta.essential) == (False, False)
    assert "прав" in editmeta.detail
    assert essential_failures(results) == []


async def test_team_options_empty_or_unmapped_is_warning(db_session):
    results = await _probe(db_session, FakeJira(worklogs=[WORKLOG], field_options=[]))
    team = next(r for r in results if r.code == "team_options")
    assert (team.ok, team.essential) == (False, False)

    results = await _probe(db_session, FakeJira(worklogs=[WORKLOG]), team_field_id=None)
    team = next(r for r in results if r.code == "team_options")
    assert team.ok is False and "не сопоставлено" in team.detail


async def test_worklogs_without_recent_data_still_ok(db_session):
    results = await _probe(db_session, FakeJira())
    worklogs = next(r for r in results if r.code == "worklogs")
    assert worklogs.ok and "не проверено" in worklogs.detail


async def test_confluence_checked_when_configured(db_session):
    db_session.add(AppSetting(key="confluence_base_url", value="https://confluence.example.test"))
    db_session.commit()

    class FakeConfluence:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get_current_user(self):
            return {"displayName": "Администратор"}

    with patch("app.connectors.confluence_client.ConfluenceClient.from_db", return_value=FakeConfluence()):
        results = await _probe(db_session, FakeJira(worklogs=[WORKLOG]))

    confluence = next(r for r in results if r.code == "confluence")
    assert confluence.ok and "Администратор" in confluence.detail
