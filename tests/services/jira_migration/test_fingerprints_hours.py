"""Отпечатки ворклогов, смещение часов облака и часы по командам и месяцам."""
from datetime import datetime, timedelta, timezone

from app.services.jira_migration.fingerprints import (
    DbWorklog,
    DcWorklog,
    detect_offset,
    minute_of,
    scan_dc_worklogs,
)
from app.services.jira_migration.hours import (
    NO_TEAM,
    compare_hours,
    hours_from_month,
    db_seconds,
    dc_seconds,
    load_db_worklogs,
    month_of_minute,
    post_check,
    to_hours,
)
from tests.services.jira_migration.factory import (
    make_employee,
    make_issue,
    make_project,
    make_worklog,
)
from tests.services.jira_migration.fake_jira import FakeJira, dc_user, dc_worklog

UTC = timezone.utc


def _db(key: str, wall: datetime, seconds: int = 3600, team: str | None = "Команда А") -> DbWorklog:
    return DbWorklog(key, minute_of(wall), seconds, "e1", team)


def _dc(key: str, utc: datetime, seconds: int = 3600) -> DcWorklog:
    return DcWorklog(key, minute_of(utc.replace(tzinfo=UTC)), seconds, "JIRAUSER1")


def test_minute_of_naive_and_aware():
    assert minute_of(datetime(1970, 1, 1, 0, 1, 59)) == 1
    msk = timezone(timedelta(hours=3))
    assert minute_of(datetime(1970, 1, 1, 3, 2, tzinfo=msk)) == 2


def test_detect_offset_finds_moscow_wall_clock():
    db_rows = [_db("OS-1", datetime(2026, 9, day, 10, 0)) for day in (10, 11, 12)]
    dc_rows = [_dc("OS-1", datetime(2026, 9, day, 7, 0)) for day in (10, 11, 12, 13)]

    offset, counts, sample = detect_offset(db_rows, dc_rows)

    assert offset == 3
    assert counts[3] == 3
    assert counts[0] == 0
    assert sample == 4
    assert detect_offset(db_rows, dc_rows).unexpected is False


def test_detect_offset_without_matches_falls_back_to_moscow():
    result = detect_offset(
        [_db("OS-1", datetime(2026, 9, 10, 10, 0))], [_dc("OS-2", datetime(2026, 9, 10, 7, 0))],
    )
    assert (result.hours, result.counts[3], result.sample, result.unexpected) == (3, 0, 1, False)


def test_detect_offset_tie_prefers_moscow_then_smaller_shift():
    dc_rows = [_dc("OS-1", datetime(2026, 9, 10, 7, 0))]

    moscow_or_minus = [_db("OS-1", datetime(2026, 9, 10, 10, 0)), _db("OS-1", datetime(2026, 9, 10, 4, 0))]
    assert detect_offset(moscow_or_minus, dc_rows).hours == 3

    two_or_minus_five = [_db("OS-1", datetime(2026, 9, 10, 9, 0)), _db("OS-1", datetime(2026, 9, 10, 2, 0))]
    result = detect_offset(two_or_minus_five, dc_rows)
    assert (result.hours, result.counts[2], result.counts[-5], result.unexpected) == (2, 1, 1, True)


def test_detect_offset_uses_sample():
    db_rows = [_db("OS-1", datetime(2026, 9, 10, 10, minute)) for minute in range(50)]
    dc_rows = [_dc("OS-1", datetime(2026, 9, 10, 7, minute)) for minute in range(50)]

    offset, counts, sample = detect_offset(db_rows, dc_rows, sample_limit=10)

    assert (offset, sample, counts[3]) == (3, 10, 10)


def test_detect_offset_sample_spreads_over_whole_list():
    dc_rows = [_dc(f"OS-{n}", datetime(2026, 9, 10, 7, 0)) for n in range(25)]
    db_rows = [_db("OS-24", datetime(2026, 9, 10, 10, 0))]

    offset, counts, sample = detect_offset(db_rows, dc_rows, sample_limit=10)

    # шаг 3 (округление вверх): 9 строк, последняя строка списка попадает в выборку
    assert (offset, sample, counts[3]) == (3, 9, 1)


def test_month_of_minute():
    assert month_of_minute(minute_of(datetime(2026, 8, 31, 23, 59))) == "2026-08"


def test_hours_by_team_and_month_with_offset():
    db_rows = [
        _db("OS-1", datetime(2026, 9, 1, 2, 30), 1800),
        _db("OS-2", datetime(2026, 9, 10, 10, 0), 3600, team=None),
    ]
    dc_rows = [_dc("OS-1", datetime(2026, 8, 31, 23, 30), 1800), _dc("OS-2", datetime(2026, 9, 10, 7, 0))]
    team_by_key = {"OS-1": "Команда А", "OS-2": None}

    assert db_seconds(db_rows) == {("Команда А", "2026-09"): 1800, (NO_TEAM, "2026-09"): 3600}
    assert dc_seconds(dc_rows, team_by_key, 3) == {("Команда А", "2026-09"): 1800, (NO_TEAM, "2026-09"): 3600}
    assert dc_seconds(dc_rows, team_by_key, 0)[("Команда А", "2026-08")] == 1800
    assert to_hours({("А", "2026-09"): 5400}) == {("А", "2026-09"): 1.5}


def test_compare_flags_differences_over_one_percent():
    rows = compare_hours(
        {("А", "2026-09"): 100.0, ("Б", "2026-08"): 10.0, ("В", "2026-07"): 0.0},
        {("А", "2026-09"): 100.5, ("Б", "2026-08"): 12.0, ("В", "2026-07"): 1.0},
    )
    assert [(r["month"], r["team"], r["diff_pct"], r["flagged"]) for r in rows] == [
        ("2026-09", "А", 0.5, False),
        ("2026-08", "Б", 20.0, True),
        ("2026-07", "В", 100.0, True),
    ]


def test_compare_exactly_one_percent_is_not_flagged():
    rows = compare_hours(
        {("А", "2026-09"): 100.0, ("Б", "2026-09"): 100.0},
        {("А", "2026-09"): 101.0, ("Б", "2026-09"): 101.01},
    )
    assert [(r["team"], r["diff_pct"], r["flagged"]) for r in rows] == [
        ("А", 1.0, False),
        ("Б", 1.01, True),
    ]


def test_load_db_worklogs(db_session):
    project = make_project(db_session)
    issue = make_issue(db_session, project, "OS-1", "1", team="Команда А")
    employee = make_employee(db_session, "acc-1", "Иванов Иван")
    employee_id = employee.id
    make_worklog(db_session, issue, employee, datetime(2026, 9, 10, 10, 0, 30), 3600, "w1")
    db_session.commit()

    assert load_db_worklogs(db_session) == [
        DbWorklog("OS-1", minute_of(datetime(2026, 9, 10, 10, 0)), 3600, employee_id, "Команда А"),
    ]


def test_post_check_compares_db_now_with_dc_from_report(db_session):
    project = make_project(db_session)
    issue = make_issue(db_session, project, "OS-1", "1", team="Команда А")
    employee = make_employee(db_session, "acc-1", "Иванов Иван")
    make_worklog(db_session, issue, employee, datetime(2026, 9, 10, 10, 0), 3600, "w1")
    db_session.commit()
    report = {"hours": {"dc_worklogs": 1, "rows": [
        {"team": "Команда А", "month": "2026-09", "db_hours": 0.0, "dc_hours": 1.0,
         "diff_pct": 100.0, "flagged": True},
    ]}}

    result = post_check(db_session, report, datetime(2026, 10, 15, 9, 0))

    assert result["checked_at"] == "2026-10-15T09:00:00Z"
    assert (result["db_worklogs"], result["dc_worklogs"]) == (1, 1)
    assert result["rows"] == [{"team": "Команда А", "month": "2026-09", "db_hours": 1.0,
                               "dc_hours": 1.0, "diff_pct": 0.0, "flagged": False}]


async def test_scan_keeps_rows_of_known_issues_and_all_authors():
    author = dc_user("JIRAUSER5", "Ivanov_I", "Иванов Иван")
    stranger = dc_user("JIRAUSER9", "Stranger", "Посторонний")
    fake = FakeJira(worklogs=[
        dc_worklog("1", "258783", author, "2026-09-10T07:00:00.000+0000", 3600),
        dc_worklog("2", "777", stranger, "2026-09-10T07:00:00.000+0000", 600),
    ])
    seen: list[int] = []

    scan = await scan_dc_worklogs(fake, {"258783": "OS-91030"}, on_progress=seen.append)

    assert scan.total == 2
    assert scan.rows == [
        DcWorklog("OS-91030", minute_of(datetime(2026, 9, 10, 7, 0, tzinfo=UTC)), 3600, "JIRAUSER5"),
    ]
    assert set(scan.authors) == {"JIRAUSER5", "JIRAUSER9"}
    assert scan.authors["JIRAUSER5"].name == "Ivanov_I"
    assert seen[-1] == 2
    assert fake.calls[0] == ("iter_worklogs_updated_since", 0)


async def test_scan_reads_started_with_moscow_offset_string():
    author = dc_user("JIRAUSER5", "Ivanov_I", "Иванов Иван")
    fake = FakeJira(worklogs=[dc_worklog("1", "258783", author, "2026-09-10T10:00:00.000+0300", 3600)])

    scan = await scan_dc_worklogs(fake, {"258783": "OS-1"})

    assert scan.rows == [
        DcWorklog("OS-1", minute_of(datetime(2026, 9, 10, 7, 0, tzinfo=UTC)), 3600, "JIRAUSER5"),
    ]
    assert detect_offset([_db("OS-1", datetime(2026, 9, 10, 10, 0))], scan.rows).hours == 3


def test_compare_skips_months_before_from_month():
    rows = compare_hours(
        {("А", "2025-12"): 1.0, ("А", "2026-01"): 2.0},
        {("А", "2025-12"): 50.0, ("А", "2026-01"): 2.0},
        from_month="2026-01",
    )
    assert [(r["month"], r["flagged"]) for r in rows] == [("2026-01", False)]


def test_hours_from_month_not_before_2026():
    assert hours_from_month({"db_worklogs_min_date": "2020-02-27"}) == "2026-01"
    assert hours_from_month({"db_worklogs_min_date": "2026-03-05"}) == "2026-03"
    assert hours_from_month({}) == "2026-01"
