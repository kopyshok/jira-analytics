"""Пробный прогон: отчёт по полям, задачам, сотрудникам и часам; данные базы не меняются."""
from datetime import datetime
from typing import Any, AsyncIterator

import pytest

from app.connectors.jira_client import (
    JiraAuthError,
    JiraClientError,
    JiraNetworkError,
    JiraRateLimitError,
    JiraServerError,
)
from app.models import AppSetting, Employee, Issue, Worklog
from app.services.jira_migration.dry_run import DryRunAborted, build_report
from app.services.jira_migration.fields import SNAPSHOT_KEY
from app.services.jira_migration.people import STATUS_BY_HOURS, STATUS_BY_NAME, STATUS_SEARCH_FAILED
from tests.services.jira_migration.factory import make_worklog
from tests.services.jira_migration.fake_jira import FakeJira, dc_worklog
from tests.services.jira_migration.world import IVANOV_DC, NOW, dc_world, seed_world


async def test_report_covers_all_sections(db_session):
    ids = seed_world(db_session)
    steps: list[str] = []

    result = await build_report(
        db_session, dc_world(), now=NOW, progress=lambda step, counters=None: steps.append(step),
    )
    report, maps = result.report, result.maps

    assert all(p["ok"] for p in report["probe"] if p["essential"])
    assert [r["cloud_id"] for r in report["fields"]] == ["customfield_11526"]
    assert report["fields"][0]["suggested_id"] == "customfield_11092"
    assert report["issues"] == {
        "db_total": 4, "matched": 2, "new_in_dc": 1, "missing": ["OS-1", "OS-2"], "project_not_found": [],
    }
    assert maps == {
        "projects": {"OS": "10901", "PMD": "10902"},
        "issues": {"OS-91030": "258783", "PMD-19591": "999999"},
    }
    assert (report["offset_hours"], report["offset_matches"], report["offset_sample"]) == (3, 4, 4)
    assert report["offset_unexpected"] is False
    people = {p["employee_id"]: p for p in report["people"]}
    assert people[ids["ivanov"]]["status"] == STATUS_BY_HOURS
    assert people[ids["ivanov"]]["auto"]["key"] == "JIRAUSER5"
    assert people[ids["petrov"]]["status"] == STATUS_BY_NAME
    assert people[ids["petrov"]]["auto"]["key"] == "JIRAUSER7"
    assert report["hours"]["rows"] == [
        {"team": "Команда А", "month": "2026-09", "db_hours": 3.0, "dc_hours": 3.0,
         "diff_pct": 0.0, "flagged": False},
        {"team": "Команда Б", "month": "2026-09", "db_hours": 0.5, "dc_hours": 0.5,
         "diff_pct": 0.0, "flagged": False},
    ]
    hours = report["hours"]
    assert (hours["db_worklogs"], hours["dc_worklogs"], hours["dc_worklogs_total"]) == (4, 4, 5)
    assert report["db_worklogs_min_date"] == "2026-09-01"
    assert report["projects"] == [{"key": "OS", "found": True}, {"key": "PMD", "found": True}]
    assert "Списания новой Jira" in steps


async def test_dry_run_writes_only_the_field_snapshot(db_session):
    seed_world(db_session)
    before = {(i.key, i.jira_issue_id) for i in db_session.query(Issue).all()}

    await build_report(db_session, dc_world(), now=NOW)

    assert {(i.key, i.jira_issue_id) for i in db_session.query(Issue).all()} == before
    assert db_session.query(Worklog).count() == 4
    snapshot = db_session.query(AppSetting).filter_by(key=SNAPSHOT_KEY).one()
    assert '"jira_team_field_id": "customfield_11526"' in snapshot.value


async def test_essential_failure_aborts_with_probe(db_session):
    seed_world(db_session)

    with pytest.raises(DryRunAborted) as exc:
        await build_report(db_session, dc_world(fail={"get_projects"}), now=NOW)

    assert "Список проектов" in str(exc.value)
    probe = {p["code"]: p for p in exc.value.report["probe"]}
    assert probe["projects"]["ok"] is False


async def test_project_absent_in_dc_is_reported_not_missing(db_session):
    seed_world(db_session)

    result = await build_report(db_session, dc_world(projects={"OS": "10901"}), now=NOW)

    issues = result.report["issues"]
    assert issues["project_not_found"] == [{"key": "PMD", "issues": 1}]
    assert issues["missing"] == ["OS-1", "OS-2"]
    assert result.maps["issues"] == {"OS-91030": "258783"}
    assert {"key": "PMD", "found": False} in result.report["projects"]


async def test_people_rows_carry_hours_on_rebound_issues(db_session):
    """Часы сотрудника на задачах, которые получат id новой Jira: при применении они удалятся
    и вернутся синком — к его карточке, только если он привязан. Часы на исчезнувших задачах не в счёт."""
    ids = seed_world(db_session)
    gone = db_session.query(Issue).filter_by(key="OS-2").one()
    make_worklog(
        db_session, gone, db_session.get(Employee, ids["petrov"]), datetime(2026, 9, 15, 10, 0), 7200, "w-gone",
    )
    db_session.commit()

    report = (await build_report(db_session, dc_world(), now=NOW)).report

    people = {p["employee_id"]: p for p in report["people"]}
    assert people[ids["ivanov"]]["hours_at_risk"] == 3.5
    assert people[ids["petrov"]]["hours_at_risk"] == 0.0


async def test_unexpected_offset_is_flagged(db_session):
    seed_world(db_session)
    utc_as_moscow = [
        dc_worklog(f"90{day}", "258783", IVANOV_DC, f"2026-09-{day}T10:00:00.000+0000", 3600)
        for day in (10, 11, 12)
    ]

    report = (await build_report(db_session, dc_world(worklogs=utc_as_moscow), now=NOW)).report

    assert report["offset_hours"] == 0
    assert report["offset_unexpected"] is True


async def test_failed_people_search_stays_in_report(db_session):
    ids = seed_world(db_session)

    report = (await build_report(db_session, dc_world(fail={"search_users"}), now=NOW)).report

    people = {p["employee_id"]: p for p in report["people"]}
    assert people[ids["petrov"]]["status"] == STATUS_SEARCH_FAILED
    assert people[ids["ivanov"]]["status"] == STATUS_BY_HOURS


class _UnavailableUserSearch(FakeJira):
    def __init__(self, error: Exception, **params: Any) -> None:
        super().__init__(**params)
        self.error = error

    async def search_users(self, query: str, max_results: int = 20, include_inactive: bool = False) -> list:
        raise self.error


def _jira(cls: type, *args: Any) -> FakeJira:
    template = dc_world()
    return cls(
        *args, projects=template.projects, issues=template.issues, worklogs=template.worklogs,
        users=template.users, fields=template.fields,
    )


@pytest.mark.parametrize(("error", "reason"), [
    (JiraAuthError("Invalid credentials"), "нет доступа"),
    (JiraRateLimitError(60), "частоту запросов"),
    (JiraNetworkError("Request failed: timeout"), "нет связи"),
    (JiraServerError("HTTP 503 GET /user/search"), "сбой на стороне новой Jira"),
])
async def test_unavailable_jira_in_people_step_aborts(db_session, error, reason):
    seed_world(db_session)

    with pytest.raises(DryRunAborted) as exc:
        await build_report(db_session, _jira(_UnavailableUserSearch, error), now=NOW)

    message = str(exc.value)
    assert "«Сотрудники»" in message and reason in message
    assert str(error) not in message
    assert exc.value.report["probe"]


async def test_issue_keys_failure_aborts(db_session):
    seed_world(db_session)

    with pytest.raises(DryRunAborted) as exc:
        await build_report(db_session, dc_world(fail={"iter_issue_keys"}), now=NOW)

    assert "«Задачи»" in str(exc.value)
    assert all(p["ok"] for p in exc.value.report["probe"] if p["essential"])


async def test_probe_sample_comes_from_project_present_in_dc(db_session):
    seed_world(db_session)
    jira = dc_world(projects={"PMD": "10902"})

    report = (await build_report(db_session, jira, now=NOW)).report

    assert all(p["ok"] for p in report["probe"] if p["essential"])
    assert ("search_issues", 'project = "PMD"') in jira.calls
    assert ("get_issue_changelog", "PMD-19591") in jira.calls
    assert report["issues"]["project_not_found"] == [{"key": "OS", "issues": 3}]


async def test_issue_checks_skipped_when_no_db_project_in_dc(db_session):
    seed_world(db_session)
    jira = dc_world(projects={"NEW": "10999"})

    report = (await build_report(db_session, jira, now=NOW)).report

    probe = {p["code"]: p for p in report["probe"]}
    assert probe["search"]["ok"] is True
    assert probe["changelog"]["detail"].startswith("Пропущено")
    assert probe["editmeta"]["detail"].startswith("Пропущено")
    assert not any(name == "get_issue_changelog" for name, _ in jira.calls)


class _TransactionWatch(FakeJira):
    """Запоминает запросы к Jira, сделанные при открытой транзакции базы."""

    def __init__(self, db: Any, **params: Any) -> None:
        super().__init__(**params)
        self.db = db
        self.in_transaction: list[str] = []

    def _call(self, name: str, arg: Any = None) -> None:
        if self.db.in_transaction():
            self.in_transaction.append(name)
        super()._call(name, arg)


async def test_long_jira_reads_run_outside_db_transaction(db_session):
    seed_world(db_session)
    jira = _jira(_TransactionWatch, db_session)

    await build_report(db_session, jira, now=NOW)

    long_reads = {"iter_issue_keys", "iter_worklogs_updated_since", "search_users"}
    assert {name for name, _ in jira.calls} >= long_reads
    assert long_reads.isdisjoint(jira.in_transaction)


class _BuggyIssueKeys(FakeJira):
    async def iter_issue_keys(self, jql: str, page_size: int = 1000) -> AsyncIterator:
        raise RuntimeError("ошибка в коде сервиса")
        yield  # pragma: no cover — генератор


async def test_code_error_is_not_disguised_as_jira_failure(db_session):
    seed_world(db_session)

    with pytest.raises(RuntimeError, match="ошибка в коде"):
        await build_report(db_session, _jira(_BuggyIssueKeys), now=NOW)


class _FieldsFailOnce(FakeJira):
    async def get_fields(self) -> list[dict]:
        if not any(name == "get_fields" for name, _ in self.calls):
            self.calls.append(("get_fields", None))
            raise JiraNetworkError("Request failed: timeout")
        return await super().get_fields()


async def test_fields_reread_when_first_request_failed(db_session):
    seed_world(db_session)

    report = (await build_report(db_session, _jira(_FieldsFailOnce), now=NOW)).report

    assert report["fields"][0]["suggested_id"] == "customfield_11092"
    assert report["dc_fields"] == [{"id": "customfield_11092", "name": "Продуктовая команда", "custom": True}]


class _BrokenWorklogScan(FakeJira):
    async def iter_worklogs_updated_since(self, since_ms: int) -> AsyncIterator:
        async for worklog in super().iter_worklogs_updated_since(since_ms):
            yield worklog
            if since_ms == 0:
                raise JiraClientError("Jira не вернула продолжение списка изменённых ворклогов")


async def test_dc_worklog_scan_failure_aborts(db_session):
    seed_world(db_session)

    with pytest.raises(DryRunAborted) as exc:
        await build_report(db_session, _jira(_BrokenWorklogScan), now=NOW)

    assert "«Списания новой Jira»" in str(exc.value)
    assert "продолжение списка" in str(exc.value)
