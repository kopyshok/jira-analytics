"""Tests for CapacityService."""

from datetime import date, timedelta

import pytest

from app.models import (
    Absence,
    Employee,
    ProductionCalendarDay,
)
from app.services.capacity_service import (
    CapacityService,
    DEFAULT_HOURS_PER_DAY,
)


@pytest.fixture
def employee(db_session):
    emp = Employee(
        jira_account_id="acc-1",
        display_name="Alice",
        is_active=True,
    )
    db_session.add(emp)
    db_session.flush()
    return emp


class TestWorkdayCalendar:
    """Simple Mon-Fri calendar (no holidays yet)."""

    def test_workdays_in_range_full_week(self, db_session):
        service = CapacityService(db_session)
        # 2026-03-02 Mon .. 2026-03-06 Fri → 5 workdays
        assert service._workdays_in_range(
            date(2026, 3, 2), date(2026, 3, 6)
        ) == 5

    def test_workdays_in_range_includes_weekend(self, db_session):
        service = CapacityService(db_session)
        # 2026-03-02 Mon .. 2026-03-08 Sun → 5 workdays
        assert service._workdays_in_range(
            date(2026, 3, 2), date(2026, 3, 8)
        ) == 5

    def test_workdays_in_range_reversed_returns_zero(self, db_session):
        service = CapacityService(db_session)
        assert service._workdays_in_range(
            date(2026, 3, 6), date(2026, 3, 2)
        ) == 0

    def test_workdays_in_month_march_2026(self, db_session):
        service = CapacityService(db_session)
        assert service._workdays_in_month(2026, 3) == 22

    def test_workdays_in_month_february_2026(self, db_session):
        service = CapacityService(db_session)
        assert service._workdays_in_month(2026, 2) == 20


class TestMonthlyCapacity:
    """Hours = workdays × 8 − vacations − mandatory."""

    def test_norm_without_deductions(self, db_session, employee):
        service = CapacityService(db_session)
        result = service.monthly_capacity(employee.id, 2026, 3)

        assert result.employee_name == "Alice"
        assert result.workdays == 22
        assert result.norm_hours == 176.0
        assert result.vacation_hours == 0.0
        assert result.mandatory_hours == 0.0
        assert result.available_hours == 176.0

    def test_vacation_inside_month(self, db_session, employee):
        # 5 workdays off
        db_session.add(
            Absence(
                employee_id=employee.id,
                start_date=date(2026, 3, 2),
                end_date=date(2026, 3, 6),
            )
        )
        db_session.flush()

        result = CapacityService(db_session).monthly_capacity(
            employee.id, 2026, 3
        )

        assert result.vacation_hours == 40.0
        assert result.available_hours == 176.0 - 40.0

    def test_vacation_spans_month_boundary(self, db_session, employee):
        # 2026-02-26 Thu .. 2026-03-06 Fri
        # Feb part: 26, 27 → 2 workdays (16h)
        # Mar part: 2, 3, 4, 5, 6 → 5 workdays (40h)
        db_session.add(
            Absence(
                employee_id=employee.id,
                start_date=date(2026, 2, 26),
                end_date=date(2026, 3, 6),
            )
        )
        db_session.flush()

        service = CapacityService(db_session)

        feb = service.monthly_capacity(employee.id, 2026, 2)
        mar = service.monthly_capacity(employee.id, 2026, 3)

        assert feb.vacation_hours == 16.0
        assert mar.vacation_hours == 40.0

    def test_available_never_negative(self, db_session, employee):
        # Full-month vacation covers all 22 workdays
        db_session.add(
            Absence(
                employee_id=employee.id,
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 31),
            )
        )
        db_session.flush()

        result = CapacityService(db_session).monthly_capacity(
            employee.id, 2026, 3
        )

        assert result.vacation_hours == 176.0
        assert result.available_hours == 0.0

    def test_unknown_employee_raises(self, db_session):
        service = CapacityService(db_session)
        with pytest.raises(ValueError, match="not found"):
            service.monthly_capacity("nonexistent", 2026, 3)

    def test_invalid_month_raises(self, db_session, employee):
        service = CapacityService(db_session)
        with pytest.raises(ValueError, match="Month"):
            service.monthly_capacity(employee.id, 2026, 13)


class TestQuarterCapacity:
    """Quarter aggregates three months."""

    def test_q1_without_deductions(self, db_session, employee):
        service = CapacityService(db_session)
        result = service.quarter_capacity(employee.id, 2026, 1)

        # Jan 22 + Feb 20 + Mar 22 = 64 workdays × 8h = 512h
        assert len(result.months) == 3
        assert result.total_norm_hours == 512.0
        assert result.total_available_hours == 512.0
        assert result.months[0].month == 1
        assert result.months[2].month == 3

    def test_q1_with_vacation_only(self, db_session, employee):
        # Vacation-only quarter aggregation; mandatory rules проверяются
        # в test_capacity_service_mandatory.py
        db_session.add(
            Absence(
                employee_id=employee.id,
                start_date=date(2026, 2, 2),
                end_date=date(2026, 2, 13),
            )
        )
        db_session.flush()

        result = CapacityService(db_session).quarter_capacity(
            employee.id, 2026, 1
        )

        assert result.total_vacation_hours == 80.0
        assert result.total_mandatory_hours == 0.0
        assert result.total_available_hours == pytest.approx(512.0 - 80.0)

    def test_invalid_quarter_raises(self, db_session, employee):
        service = CapacityService(db_session)
        with pytest.raises(ValueError, match="Quarter"):
            service.quarter_capacity(employee.id, 2026, 5)


class TestTeamCapacity:
    def test_active_only_by_default(self, db_session):
        active = Employee(
            jira_account_id="a1", display_name="Alice", is_active=True
        )
        inactive = Employee(
            jira_account_id="b1", display_name="Bob", is_active=False
        )
        db_session.add_all([active, inactive])
        db_session.flush()

        results = CapacityService(db_session).team_quarter_capacity(2026, 1)

        assert len(results) == 1
        assert results[0].employee_name == "Alice"

    def test_explicit_employee_ids(self, db_session):
        alice = Employee(
            jira_account_id="a1", display_name="Alice", is_active=True
        )
        bob = Employee(
            jira_account_id="b1", display_name="Bob", is_active=False
        )
        db_session.add_all([alice, bob])
        db_session.flush()

        results = CapacityService(db_session).team_quarter_capacity(
            2026, 1, employee_ids=[bob.id]
        )

        assert len(results) == 1
        assert results[0].employee_name == "Bob"


class TestHoursPerDayOverride:
    def test_six_hour_workday(self, db_session, employee):
        service = CapacityService(db_session, hours_per_day=6.0)
        result = service.monthly_capacity(employee.id, 2026, 3)

        assert result.norm_hours == 22 * 6.0
        assert DEFAULT_HOURS_PER_DAY == 8.0


def _naive_weekday_count(start: date, end: date) -> int:
    n, d = 0, start
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


class TestWorkdayCalendarIntegration:
    def test_holidays_reduce_workday_count(self, db_session, employee):
        holiday_dates = [date(2026, 1, d) for d in range(1, 9)]
        for d in holiday_dates:
            db_session.add(ProductionCalendarDay(
                date=d, is_workday=False, kind="holiday",
                note="НГ", source="xmlcalendar",
            ))
        db_session.commit()

        svc = CapacityService(db_session)
        got = svc._workdays_in_range(date(2026, 1, 1), date(2026, 1, 31))

        baseline = _naive_weekday_count(date(2026, 1, 1), date(2026, 1, 31))
        weekday_holidays = sum(1 for d in holiday_dates if d.weekday() < 5)
        assert got == baseline - weekday_holidays

    def test_weekend_overridden_to_workday(self, db_session, employee):
        db_session.add(ProductionCalendarDay(
            date=date(2026, 3, 7), is_workday=True,
            kind="workday_moved", note="перенос", source="xmlcalendar",
        ))
        db_session.commit()
        svc = CapacityService(db_session)
        got = svc._workdays_in_range(date(2026, 3, 7), date(2026, 3, 7))
        assert got == 1

    def test_norm_hours_uses_preholiday_7h(self, db_session, employee):
        """Предпраздничный день даёт 7ч нормы, а не 8."""
        # Вся февральская сетка 2026. 20 февраля 2026 — пятница, предпраздничный.
        for d in range(1, 29):
            day = date(2026, 2, d)
            if day == date(2026, 2, 20):
                kind, is_wd, hours = "preholiday", True, 7.0
            elif day.weekday() < 5:
                kind, is_wd, hours = "workday", True, 8.0
            else:
                kind, is_wd, hours = "weekend", False, 0.0
            db_session.add(ProductionCalendarDay(
                date=day, is_workday=is_wd, kind=kind, hours=hours,
                source="xmlcalendar",
            ))
        db_session.commit()

        svc = CapacityService(db_session)
        norm = svc._norm_hours_in_month(2026, 2)
        workdays = svc._workdays_in_month(2026, 2)
        # 20 рабочих дней, из них 1 по 7 часов — 19×8 + 7 = 159
        assert workdays == 20
        assert norm == 19 * 8 + 7


from datetime import datetime

from app.models import Issue, Project, Worklog


class TestMonthlyCapacityFact:
    def test_fact_hours_sums_worklogs_in_month(self, db_session, employee):
        proj = Project(id="p", jira_project_id="10", key="P", name="P")
        issue = Issue(id="i", jira_issue_id="1", key="P-1", summary="x",
                      project_id=proj.id, issue_type="Task", status="В работе")
        db_session.add_all([proj, issue])
        db_session.flush()
        db_session.add_all([
            Worklog(id="w1", jira_worklog_id="1", issue_id=issue.id,
                    employee_id=employee.id,
                    started_at=datetime(2026, 1, 15, 10, 0),
                    hours=4.0, time_spent_seconds=14400),
            Worklog(id="w2", jira_worklog_id="2", issue_id=issue.id,
                    employee_id=employee.id,
                    started_at=datetime(2026, 1, 20, 10, 0),
                    hours=3.0, time_spent_seconds=10800),
            Worklog(id="w3", jira_worklog_id="3", issue_id=issue.id,
                    employee_id=employee.id,
                    started_at=datetime(2026, 2, 1, 10, 0),
                    hours=2.0, time_spent_seconds=7200),
        ])
        db_session.commit()

        svc = CapacityService(db_session)
        mc = svc.monthly_capacity(employee.id, 2026, 1)
        assert mc.fact_hours == 7.0

    def test_fact_hours_zero_when_no_worklogs(self, db_session, employee):
        svc = CapacityService(db_session)
        mc = svc.monthly_capacity(employee.id, 2026, 3)
        assert mc.fact_hours == 0.0

    def test_quarter_fact_sums_months(self, db_session, employee):
        proj = Project(id="pp", jira_project_id="20", key="PP", name="PP")
        issue = Issue(id="ii", jira_issue_id="2", key="PP-1", summary="x",
                      project_id=proj.id, issue_type="Task", status="В работе")
        db_session.add_all([proj, issue])
        db_session.flush()
        for month, day, h in [(1, 10, 5.0), (2, 10, 4.0), (3, 10, 3.0)]:
            db_session.add(Worklog(
                id=f"w{month}", jira_worklog_id=f"k{month}",
                issue_id=issue.id, employee_id=employee.id,
                started_at=datetime(2026, month, day, 10, 0),
                hours=h, time_spent_seconds=int(h * 3600),
            ))
        db_session.commit()

        svc = CapacityService(db_session)
        qc = svc.quarter_capacity(employee.id, 2026, 1)
        assert qc.total_fact_hours == 12.0


class TestTeamCapacityIncludesTeamField:
    def test_team_field_populated(self, db_session):
        e1 = Employee(
            id="e1",
            jira_account_id="a1",
            display_name="Иванов",
            is_active=True,
            team="Alpha",
        )
        e2 = Employee(
            id="e2",
            jira_account_id="a2",
            display_name="Петров",
            is_active=True,
            team=None,
        )
        db_session.add_all([e1, e2])
        db_session.commit()

        svc = CapacityService(db_session)
        rows = svc.team_quarter_capacity(2026, 2)
        by_id = {r.employee_id: r for r in rows}
        assert by_id["e1"].team == "Alpha"
        assert by_id["e2"].team is None


class TestCategoryBreakdown:
    def test_breakdown_buckets(self, db_session, employee):
        from app.models import Category
        db_session.add_all([
            Category(id="c1", code="active_1", label="Active", is_system=False),
            Category(id="c2", code="archive", label="Archive", is_system=True),
            Category(id="c3", code="archive_target", label="ArchTarget", is_system=True),
            Category(id="c4", code="initiatives_rfa", label="Init", is_system=True),
        ])
        proj = Project(id="px", jira_project_id="30", key="X", name="X")
        issue_act = Issue(id="i_act", jira_issue_id="7001", key="X-1", summary="x",
                          project_id=proj.id, issue_type="Task", status="В работе",
                          assigned_category="active_1")
        issue_arch_t = Issue(id="i_atg", jira_issue_id="7002", key="X-2", summary="x",
                             project_id=proj.id, issue_type="Task", status="В работе",
                             assigned_category="archive_target")
        issue_null = Issue(id="i_nul", jira_issue_id="7003", key="X-3", summary="x",
                           project_id=proj.id, issue_type="Task", status="В работе",
                           assigned_category=None)
        db_session.add_all([proj, issue_act, issue_arch_t, issue_null])
        db_session.flush()
        db_session.add_all([
            Worklog(id="wa", jira_worklog_id="a", issue_id=issue_act.id,
                    employee_id=employee.id,
                    started_at=datetime(2026, 1, 10, 10, 0),
                    hours=10.0, time_spent_seconds=36000),
            Worklog(id="wt", jira_worklog_id="t", issue_id=issue_arch_t.id,
                    employee_id=employee.id,
                    started_at=datetime(2026, 2, 10, 10, 0),
                    hours=5.0, time_spent_seconds=18000),
            Worklog(id="wn", jira_worklog_id="n", issue_id=issue_null.id,
                    employee_id=employee.id,
                    started_at=datetime(2026, 3, 10, 10, 0),
                    hours=2.0, time_spent_seconds=7200),
        ])
        db_session.commit()

        svc = CapacityService(db_session)
        rows = svc.category_breakdown(2026, 1)
        row = next(r for r in rows if r.employee_id == employee.id)
        assert row.by_bucket == {
            "active_stack": 10.0,
            "initiatives": 0.0,
            "archive_target": 5.0,
            "archive_other": 0.0,
            "uncategorized": 2.0,
        }
        assert row.total_hours == 17.0
