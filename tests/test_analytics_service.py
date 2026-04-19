"""Tests for AnalyticsService."""

from datetime import datetime

import pytest

from app.models import (
    CategoryMapping,
    Employee,
    EmployeeTeam,
    Issue,
    Project,
    Worklog,
)
from app.services.analytics_service import AnalyticsService
from app.services.categories import CategoryCode


@pytest.fixture
def setup_data(db_session):
    """Seed two employees, two projects, three issues, and several worklogs."""
    alice = Employee(jira_account_id="a1", display_name="Alice")
    bob = Employee(jira_account_id="b1", display_name="Bob")
    db_session.add_all([alice, bob])

    db_session.flush()  # Need alice.id/bob.id for EmployeeTeam
    db_session.add_all([
        EmployeeTeam(employee_id=alice.id, team="Core", is_primary=True),
        EmployeeTeam(employee_id=bob.id, team="Mobile", is_primary=True),
    ])

    proj_a = Project(jira_project_id="pa", key="AAA", name="Alpha")
    proj_b = Project(jira_project_id="pb", key="BBB", name="Beta")
    db_session.add_all([proj_a, proj_b])
    db_session.flush()

    issue_a1 = Issue(
        jira_issue_id="ja1",
        key="AAA-1",
        summary="A1",
        issue_type="Task",
        status="Open",
        project_id=proj_a.id,
        team="Core",
        participating_teams='["Core","Mobile"]',
    )
    issue_a2 = Issue(
        jira_issue_id="ja2",
        key="AAA-2",
        summary="A2",
        issue_type="Task",
        status="Open",
        project_id=proj_a.id,
        team="Mobile",
        participating_teams='["Mobile"]',
    )
    issue_b1 = Issue(
        jira_issue_id="jb1",
        key="BBB-1",
        summary="B1",
        issue_type="Task",
        status="Open",
        project_id=proj_b.id,
        team=None,
        participating_teams='[]',
    )
    db_session.add_all([issue_a1, issue_a2, issue_b1])
    db_session.flush()

    # Alice: 2h AAA-1 (Jan 5), 3h AAA-2 (Jan 6), 1h BBB-1 (Jan 7)
    # Bob:   4h BBB-1 (Jan 5), 2h AAA-1 (Jan 8)
    worklogs = [
        Worklog(
            jira_worklog_id="wl1",
            started_at=datetime(2026, 1, 5, 10, 0, 0),
            hours=2.0,
            time_spent_seconds=7200,
            comment_text="work a1",
            issue_id=issue_a1.id,
            employee_id=alice.id,
        ),
        Worklog(
            jira_worklog_id="wl2",
            started_at=datetime(2026, 1, 6, 10, 0, 0),
            hours=3.0,
            time_spent_seconds=10800,
            comment_text="work a2",
            issue_id=issue_a2.id,
            employee_id=alice.id,
        ),
        Worklog(
            jira_worklog_id="wl3",
            started_at=datetime(2026, 1, 7, 10, 0, 0),
            hours=1.0,
            time_spent_seconds=3600,
            comment_text="work b1",
            issue_id=issue_b1.id,
            employee_id=alice.id,
        ),
        Worklog(
            jira_worklog_id="wl4",
            started_at=datetime(2026, 1, 5, 9, 0, 0),
            hours=4.0,
            time_spent_seconds=14400,
            comment_text="work b1 bob",
            issue_id=issue_b1.id,
            employee_id=bob.id,
        ),
        Worklog(
            jira_worklog_id="wl5",
            started_at=datetime(2026, 1, 8, 9, 0, 0),
            hours=2.0,
            time_spent_seconds=7200,
            comment_text="work a1 bob",
            issue_id=issue_a1.id,
            employee_id=bob.id,
        ),
    ]
    db_session.add_all(worklogs)
    db_session.flush()

    # Category mappings for worklogs
    db_session.add_all([
        CategoryMapping(
            entity_type="worklog",
            entity_id=worklogs[0].id,
            category=CategoryCode.TECH_DEBT,
        ),
        CategoryMapping(
            entity_type="worklog",
            entity_id=worklogs[1].id,
            category=CategoryCode.TECH_DEBT,
        ),
        CategoryMapping(
            entity_type="worklog",
            entity_id=worklogs[2].id,
            category=CategoryCode.MEETINGS,
        ),
        CategoryMapping(
            entity_type="worklog",
            entity_id=worklogs[3].id,
            category=CategoryCode.MEETINGS,
        ),
        CategoryMapping(
            entity_type="worklog",
            entity_id=worklogs[4].id,
            category=CategoryCode.SUPPORT_CONSULTATION,
        ),
    ])
    db_session.flush()

    return {
        "alice": alice,
        "bob": bob,
        "proj_a": proj_a,
        "proj_b": proj_b,
        "worklogs": worklogs,
    }


class TestHoursByEmployee:
    def test_totals(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_employee()

        by_name = {row.label: row for row in rows}
        assert by_name["Alice"].total_hours == 6.0
        assert by_name["Alice"].worklog_count == 3
        assert by_name["Bob"].total_hours == 6.0
        assert by_name["Bob"].worklog_count == 2

    def test_date_filter(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_employee(
            start=datetime(2026, 1, 7, 0, 0, 0),
            end=datetime(2026, 1, 31, 0, 0, 0),
        )

        by_name = {row.label: row for row in rows}
        # Alice: only wl3 (1h on Jan 7)
        # Bob: only wl5 (2h on Jan 8)
        assert by_name["Alice"].total_hours == 1.0
        assert by_name["Bob"].total_hours == 2.0

    def test_team_filter_employees_only(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_employee(
            teams=["Core"],
            match_employees=True,
            match_issues=False,
        )
        by_name = {r.label: r for r in rows}
        assert "Alice" in by_name  # Alice is in Core
        assert "Bob" not in by_name  # Bob is in Mobile
        assert by_name["Alice"].total_hours == 6.0  # all Alice's worklogs

    def test_team_filter_issues_only(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_employee(
            teams=["Mobile"],
            match_employees=False,
            match_issues=True,
        )
        by_name = {r.label: r for r in rows}
        # Mobile issues: AAA-2 (team=Mobile) + BBB-1 via participating_teams? BBB-1 has team=None, participating_teams='[]'
        # Actually AAA-1 has participating_teams='["Core","Mobile"]' — so Mobile matches AAA-1 too.
        # Worklogs on AAA-1: Alice 2h + Bob 2h; on AAA-2: Alice 3h; BBB-1: none.
        # So Alice total = 5h (AAA-1 + AAA-2), Bob total = 2h (AAA-1)
        assert by_name["Alice"].total_hours == 5.0
        assert by_name["Bob"].total_hours == 2.0

    def test_team_filter_union(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_employee(
            teams=["Core"],
            match_employees=True,
            match_issues=True,
        )
        by_name = {r.label: r for r in rows}
        # Alice (Core member) -> all her worklogs (6h)
        # Bob (not Core member), but AAA-1 has team=Core (via participating_teams) and worklog wl5 on AAA-1 -> 2h
        # BBB-1 has no Core team -> Bob's wl4 (4h on BBB-1) excluded
        assert by_name["Alice"].total_hours == 6.0
        assert by_name["Bob"].total_hours == 2.0

    def test_team_filter_none_token_employees(self, db_session, setup_data):
        # Add an employee with no team memberships
        carol = Employee(jira_account_id="c1", display_name="Carol")
        db_session.add(carol)
        db_session.flush()
        # Give Carol a worklog on AAA-1
        db_session.add(Worklog(
            jira_worklog_id="wl6",
            started_at=datetime(2026, 1, 9, 10, 0, 0),
            hours=1.5,
            time_spent_seconds=5400,
            comment_text="carol",
            issue_id=setup_data["worklogs"][0].issue_id,  # AAA-1
            employee_id=carol.id,
        ))
        db_session.flush()

        service = AnalyticsService(db_session)
        rows = service.hours_by_employee(
            teams=["__none__"],
            match_employees=True,
            match_issues=False,
        )
        by_name = {r.label: r for r in rows}
        assert "Carol" in by_name
        assert by_name["Carol"].total_hours == 1.5
        assert "Alice" not in by_name
        assert "Bob" not in by_name

    def test_team_filter_none_token_issues(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_employee(
            teams=["__none__"],
            match_employees=False,
            match_issues=True,
        )
        by_name = {r.label: r for r in rows}
        # Only BBB-1 has no team; worklogs on BBB-1: Alice wl3 (1h) + Bob wl4 (4h)
        assert by_name["Alice"].total_hours == 1.0
        assert by_name["Bob"].total_hours == 4.0

    def test_team_filter_empty_teams_is_noop(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows_filtered = service.hours_by_employee(teams=[], match_employees=True, match_issues=True)
        rows_baseline = service.hours_by_employee()
        # totals identical
        assert sum(r.total_hours for r in rows_filtered) == sum(r.total_hours for r in rows_baseline)

    def test_team_filter_both_flags_off_is_noop(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows_filtered = service.hours_by_employee(
            teams=["Core"], match_employees=False, match_issues=False,
        )
        rows_baseline = service.hours_by_employee()
        assert sum(r.total_hours for r in rows_filtered) == sum(r.total_hours for r in rows_baseline)

    def test_team_filter_issues_escaped_team_name(self, db_session, setup_data):
        # Add an issue whose participating_teams contains a name with a quote
        extra = Issue(
            jira_issue_id="jx",
            key="AAA-X",
            summary="X",
            issue_type="Task",
            status="Open",
            project_id=setup_data["proj_a"].id,
            team=None,
            participating_teams='["Team \\"Quoted\\""]',  # JSON: ["Team \"Quoted\""]
        )
        db_session.add(extra)
        db_session.flush()
        db_session.add(Worklog(
            jira_worklog_id="wlx",
            started_at=datetime(2026, 1, 10, 10, 0, 0),
            hours=1.0,
            time_spent_seconds=3600,
            comment_text="x",
            issue_id=extra.id,
            employee_id=setup_data["alice"].id,
        ))
        db_session.flush()

        service = AnalyticsService(db_session)
        rows = service.hours_by_employee(
            teams=['Team "Quoted"'],
            match_employees=False,
            match_issues=True,
        )
        by_name = {r.label: r for r in rows}
        # Only wlx matches (1h). Other worklogs are on AAA-1/AAA-2/BBB-1 which don't have this team.
        assert by_name["Alice"].total_hours == 1.0
        assert "Bob" not in by_name


class TestHoursByProject:
    def test_totals(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_project()

        by_name = {row.label: row for row in rows}
        # Alpha: Alice 2+3 + Bob 2 = 7
        # Beta: Alice 1 + Bob 4 = 5
        assert by_name["Alpha"].total_hours == 7.0
        assert by_name["Beta"].total_hours == 5.0


class TestHoursByCategory:
    def test_totals(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_category()

        by_key = {row.key: row for row in rows}
        # tech_debt: 2 + 3 = 5
        # meetings: 1 + 4 = 5
        # support: 2
        assert by_key[CategoryCode.TECH_DEBT].total_hours == 5.0
        assert by_key[CategoryCode.MEETINGS].total_hours == 5.0
        assert by_key[CategoryCode.SUPPORT_CONSULTATION].total_hours == 2.0

    def test_labels_are_russian(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_category()

        tech_debt = next(r for r in rows if r.key == CategoryCode.TECH_DEBT)
        assert tech_debt.label == "Технический долг / прочее"


class TestHoursByPeriod:
    def test_by_day(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_period(period="day")

        by_day = {row.key: row.total_hours for row in rows}
        # Jan 5: 2 (Alice) + 4 (Bob) = 6
        # Jan 6: 3
        # Jan 7: 1
        # Jan 8: 2
        assert by_day["2026-01-05"] == 6.0
        assert by_day["2026-01-06"] == 3.0
        assert by_day["2026-01-07"] == 1.0
        assert by_day["2026-01-08"] == 2.0

    def test_by_month(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.hours_by_period(period="month")

        assert len(rows) == 1
        assert rows[0].key == "2026-01"
        assert rows[0].total_hours == 12.0


class TestContextSwitching:
    def test_counts(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.context_switching()

        by_name = {row.employee_name: row for row in rows}

        # Alice: Jan 5 Alpha -> Jan 6 Alpha -> Jan 7 Beta => 1 switch
        alice = by_name["Alice"]
        assert alice.total_worklogs == 3
        assert alice.distinct_projects == 2
        assert alice.switches == 1
        assert alice.distinct_categories == 2  # tech_debt, meetings

        # Bob: Jan 5 Beta -> Jan 8 Alpha => 1 switch
        bob = by_name["Bob"]
        assert bob.total_worklogs == 2
        assert bob.distinct_projects == 2
        assert bob.switches == 1
        assert bob.distinct_categories == 2  # meetings, support_consultation

    def test_date_filter_reduces_switches(self, db_session, setup_data):
        service = AnalyticsService(db_session)
        rows = service.context_switching(
            start=datetime(2026, 1, 5, 0, 0, 0),
            end=datetime(2026, 1, 6, 23, 59, 59),
        )

        by_name = {row.employee_name: row for row in rows}
        # Alice: Jan 5 Alpha, Jan 6 Alpha => no switch
        assert by_name["Alice"].switches == 0
        # Bob: only Jan 5 Beta => no switch
        assert by_name["Bob"].switches == 0


class TestEmployeeFilter:
    """Фильтр employee_id сужает результаты до одного сотрудника."""

    def test_hours_by_employee(self, db_session, setup_data):
        alice = setup_data["alice"]
        rows = AnalyticsService(db_session).hours_by_employee(employee_id=alice.id)
        assert len(rows) == 1
        assert rows[0].label == "Alice"
        assert rows[0].total_hours == 6.0

    def test_hours_by_project(self, db_session, setup_data):
        # Alice: 2+3=5h на Alpha, 1h на Beta
        alice = setup_data["alice"]
        rows = AnalyticsService(db_session).hours_by_project(employee_id=alice.id)
        by_name = {r.label: r for r in rows}
        assert by_name["Alpha"].total_hours == 5.0
        assert by_name["Beta"].total_hours == 1.0
        assert "Bob" not in {r.label for r in rows}

    def test_hours_by_category(self, db_session, setup_data):
        # Alice: wl1(tech_debt 2h), wl2(tech_debt 3h), wl3(meetings 1h)
        alice = setup_data["alice"]
        rows = AnalyticsService(db_session).hours_by_category(employee_id=alice.id)
        by_key = {r.key: r for r in rows}
        assert by_key[CategoryCode.TECH_DEBT].total_hours == 5.0
        assert by_key[CategoryCode.MEETINGS].total_hours == 1.0
        assert CategoryCode.SUPPORT_CONSULTATION not in by_key  # только у Bob

    def test_hours_by_period(self, db_session, setup_data):
        # Alice: Jan5=2h, Jan6=3h, Jan7=1h
        alice = setup_data["alice"]
        rows = AnalyticsService(db_session).hours_by_period(period="day", employee_id=alice.id)
        by_day = {r.key: r.total_hours for r in rows}
        assert by_day["2026-01-05"] == 2.0
        assert by_day["2026-01-06"] == 3.0
        assert by_day["2026-01-07"] == 1.0
        assert "2026-01-08" not in by_day  # Bob only

    def test_context_switching(self, db_session, setup_data):
        alice = setup_data["alice"]
        rows = AnalyticsService(db_session).context_switching(employee_id=alice.id)
        assert len(rows) == 1
        assert rows[0].employee_name == "Alice"


class TestProjectFilter:
    """Фильтр project_key сужает результаты до одного проекта."""

    def test_hours_by_project(self, db_session, setup_data):
        # AAA: Alice 5h + Bob 2h = 7h
        rows = AnalyticsService(db_session).hours_by_project(project_key="AAA")
        assert len(rows) == 1
        assert rows[0].label == "Alpha"
        assert rows[0].total_hours == 7.0

    def test_hours_by_employee(self, db_session, setup_data):
        # AAA worklogs: Alice wl1(2h) + wl2(3h) = 5h, Bob wl5(2h)
        rows = AnalyticsService(db_session).hours_by_employee(project_key="AAA")
        by_name = {r.label: r for r in rows}
        assert by_name["Alice"].total_hours == 5.0
        assert by_name["Bob"].total_hours == 2.0

    def test_hours_by_category(self, db_session, setup_data):
        # AAA: wl1(tech_debt 2h), wl2(tech_debt 3h), wl5(support 2h) — wl3/wl4 из BBB не входят
        rows = AnalyticsService(db_session).hours_by_category(project_key="AAA")
        by_key = {r.key: r for r in rows}
        assert by_key[CategoryCode.TECH_DEBT].total_hours == 5.0
        assert by_key[CategoryCode.SUPPORT_CONSULTATION].total_hours == 2.0
        assert CategoryCode.MEETINGS not in by_key  # wl3 и wl4 — из BBB

    def test_hours_by_period(self, db_session, setup_data):
        # AAA: Jan5=2h(wl1), Jan6=3h(wl2), Jan8=2h(wl5)
        rows = AnalyticsService(db_session).hours_by_period(period="day", project_key="AAA")
        by_day = {r.key: r.total_hours for r in rows}
        assert by_day["2026-01-05"] == 2.0
        assert by_day["2026-01-06"] == 3.0
        assert by_day["2026-01-08"] == 2.0
        assert "2026-01-07" not in by_day  # wl3 — BBB

    def test_context_switching(self, db_session, setup_data):
        # AAA: Alice wl1(AAA-1 Jan5) + wl2(AAA-2 Jan6) — оба Alpha, 0 switches
        #       Bob wl5(AAA-1 Jan8) — один worklog, 0 switches
        rows = AnalyticsService(db_session).context_switching(project_key="AAA")
        by_name = {r.employee_name: r for r in rows}
        assert by_name["Alice"].total_worklogs == 2
        assert by_name["Alice"].switches == 0
        assert by_name["Bob"].total_worklogs == 1
        assert by_name["Bob"].switches == 0
