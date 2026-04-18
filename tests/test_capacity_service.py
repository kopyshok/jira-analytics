"""Tests for CapacityService."""

from datetime import date, timedelta

import pytest

from app.models import (
    Employee,
    MonthlyCapacityRule,
    ProductionCalendarDay,
    Vacation,
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
            Vacation(
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
            Vacation(
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

    def test_mandatory_rule_applied(self, db_session, employee):
        # 20% of norm is mandatory
        db_session.add(
            MonthlyCapacityRule(year=2026, month=3, percent_of_norm=20.0)
        )
        db_session.flush()

        result = CapacityService(db_session).monthly_capacity(
            employee.id, 2026, 3
        )

        assert result.mandatory_hours == 176.0 * 0.2
        assert result.available_hours == 176.0 - 176.0 * 0.2

    def test_vacation_and_mandatory_combined(self, db_session, employee):
        db_session.add(
            Vacation(
                employee_id=employee.id,
                start_date=date(2026, 3, 2),
                end_date=date(2026, 3, 6),
            )
        )
        db_session.add(
            MonthlyCapacityRule(year=2026, month=3, percent_of_norm=25.0)
        )
        db_session.flush()

        result = CapacityService(db_session).monthly_capacity(
            employee.id, 2026, 3
        )

        assert result.vacation_hours == 40.0
        assert result.mandatory_hours == 44.0  # 176 * 0.25
        assert result.available_hours == 176.0 - 40.0 - 44.0

    def test_available_never_negative(self, db_session, employee):
        # Full-month vacation covers all 22 workdays
        db_session.add(
            Vacation(
                employee_id=employee.id,
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 31),
            )
        )
        db_session.add(
            MonthlyCapacityRule(year=2026, month=3, percent_of_norm=50.0)
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

    def test_q1_with_vacation_and_rule(self, db_session, employee):
        db_session.add(
            Vacation(
                employee_id=employee.id,
                start_date=date(2026, 2, 2),
                end_date=date(2026, 2, 13),
            )
        )
        # 10 workdays in Feb → 80h
        db_session.add(
            MonthlyCapacityRule(year=2026, month=1, percent_of_norm=10.0)
        )
        # Jan: 22 × 8 = 176, mandatory 17.6
        db_session.flush()

        result = CapacityService(db_session).quarter_capacity(
            employee.id, 2026, 1
        )

        assert result.total_vacation_hours == 80.0
        assert result.total_mandatory_hours == 17.6
        assert result.total_available_hours == pytest.approx(
            512.0 - 80.0 - 17.6
        )

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
