"""Tests for PlanningService — greedy backlog packing."""

import pytest

from app.models import (
    BacklogItem,
    Employee,
    PlanningScenario,
    ScenarioAllocation,
)
from app.services.planning_service import PlanningService


@pytest.fixture
def two_employees(db_session):
    """Две активных сотрудника → 2 × 512 = 1024 часа ёмкости за Q1 2026."""
    alice = Employee(
        jira_account_id="a1", display_name="Alice", is_active=True
    )
    bob = Employee(
        jira_account_id="b1", display_name="Bob", is_active=True
    )
    db_session.add_all([alice, bob])
    db_session.flush()
    return alice, bob


def _add_item(db, *, title, priority, hours, year=2026, quarter="Q1"):
    item = BacklogItem(
        title=title,
        priority=priority,
        estimate_hours=hours,
        year=year,
        quarter=quarter,
    )
    db.add(item)
    db.flush()
    return item


class TestTeamCapacityBasis:
    """Сервис опирается на CapacityService.team_quarter_capacity."""

    def test_capacity_is_zero_without_employees(self, db_session):
        service = PlanningService(db_session)
        result = service.generate_scenario("empty", 2026, 1)

        assert result.total_capacity_hours == 0.0
        assert result.total_planned_hours == 0.0
        assert result.allocations == []

    def test_capacity_sums_team(self, db_session, two_employees):
        service = PlanningService(db_session)
        result = service.generate_scenario("cap", 2026, 1)

        # 2 employees × (Jan 22 + Feb 20 + Mar 22) × 8h = 2 × 512 = 1024
        assert result.total_capacity_hours == 1024.0


class TestGreedyOrder:
    """Сортировка: priority ASC (None в конец), затем estimate ASC, title."""

    def test_lower_priority_number_packed_first(
        self, db_session, two_employees
    ):
        low = _add_item(db_session, title="low", priority=3, hours=100)
        high = _add_item(db_session, title="high", priority=1, hours=100)
        mid = _add_item(db_session, title="mid", priority=2, hours=100)

        result = PlanningService(db_session).generate_scenario(
            "ord", 2026, 1
        )

        titles_in_order = [a.title for a in result.allocations]
        assert titles_in_order == ["high", "mid", "low"]
        assert all(a.included for a in result.allocations)

    def test_none_priority_goes_last(self, db_session, two_employees):
        _add_item(db_session, title="none", priority=None, hours=10)
        _add_item(db_session, title="p5", priority=5, hours=10)

        result = PlanningService(db_session).generate_scenario(
            "ord", 2026, 1
        )

        assert [a.title for a in result.allocations] == ["p5", "none"]


class TestGreedyPacking:
    def test_all_fit(self, db_session, two_employees):
        _add_item(db_session, title="a", priority=1, hours=100)
        _add_item(db_session, title="b", priority=2, hours=200)
        _add_item(db_session, title="c", priority=3, hours=300)

        result = PlanningService(db_session).generate_scenario(
            "fit", 2026, 1
        )

        assert result.included_count == 3
        assert result.skipped_count == 0
        assert result.total_planned_hours == 600.0
        assert result.leftover_capacity_hours == 1024.0 - 600.0
        assert all(a.reason == "fit" for a in result.allocations)

    def test_last_item_overflows_and_is_skipped(
        self, db_session, two_employees
    ):
        _add_item(db_session, title="big1", priority=1, hours=700)
        _add_item(db_session, title="big2", priority=2, hours=400)  # overflow
        _add_item(db_session, title="small", priority=3, hours=50)

        result = PlanningService(db_session).generate_scenario(
            "overflow", 2026, 1
        )

        by_title = {a.title: a for a in result.allocations}
        assert by_title["big1"].included is True
        assert by_title["big2"].included is False
        assert by_title["big2"].reason == "no_capacity_left"
        # 1024 − 700 = 324, small=50 still fits after skipping big2
        assert by_title["small"].included is True
        assert result.total_planned_hours == 750.0

    def test_no_estimate_is_skipped_with_reason(
        self, db_session, two_employees
    ):
        _add_item(db_session, title="unknown", priority=1, hours=None)
        _add_item(db_session, title="zero", priority=2, hours=0)
        _add_item(db_session, title="real", priority=3, hours=40)

        result = PlanningService(db_session).generate_scenario(
            "missing-est", 2026, 1
        )

        by_title = {a.title: a for a in result.allocations}
        assert by_title["unknown"].included is False
        assert by_title["unknown"].reason == "no_estimate"
        assert by_title["zero"].included is False
        assert by_title["zero"].reason == "no_estimate"
        assert by_title["real"].included is True
        assert result.total_planned_hours == 40.0


class TestFiltering:
    def test_only_matching_year_and_quarter_considered(
        self, db_session, two_employees
    ):
        _add_item(
            db_session, title="in", priority=1, hours=10, year=2026, quarter="Q1"
        )
        _add_item(
            db_session,
            title="other-q",
            priority=1,
            hours=10,
            year=2026,
            quarter="Q2",
        )
        _add_item(
            db_session,
            title="other-year",
            priority=1,
            hours=10,
            year=2025,
            quarter="Q1",
        )

        result = PlanningService(db_session).generate_scenario(
            "filter", 2026, 1
        )

        assert [a.title for a in result.allocations] == ["in"]

    def test_explicit_ids_override_filter(self, db_session, two_employees):
        a = _add_item(
            db_session, title="a", priority=1, hours=10, year=2026, quarter="Q2"
        )
        _add_item(
            db_session,
            title="other",
            priority=1,
            hours=10,
            year=2026,
            quarter="Q1",
        )

        result = PlanningService(db_session).generate_scenario(
            "explicit", 2026, 1, backlog_item_ids=[a.id]
        )

        assert [x.title for x in result.allocations] == ["a"]
        assert result.allocations[0].included is True


class TestPersistence:
    def test_scenario_and_allocations_are_saved(
        self, db_session, two_employees
    ):
        _add_item(db_session, title="a", priority=1, hours=10)
        _add_item(db_session, title="b", priority=2, hours=2000)  # skip

        result = PlanningService(db_session).generate_scenario(
            "save", 2026, 1
        )

        scenario = db_session.get(PlanningScenario, result.scenario_id)
        assert scenario is not None
        assert scenario.name == "save"
        assert scenario.year == 2026
        assert scenario.quarter == "Q1"

        allocations = (
            db_session.query(ScenarioAllocation)
            .filter(ScenarioAllocation.scenario_id == scenario.id)
            .all()
        )
        assert len(allocations) == 2
        included_flags = {a.included_flag for a in allocations}
        assert included_flags == {True, False}


class TestValidation:
    def test_invalid_quarter_raises(self, db_session, two_employees):
        service = PlanningService(db_session)
        with pytest.raises(ValueError, match="Quarter"):
            service.generate_scenario("bad", 2026, 5)
