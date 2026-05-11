"""Verify PlanningService reads effective hours and helpers."""
from app.services.planning_service import PlanningService, should_skip_in_plan


class FakeBI:
    estimate_analyst_hours = 40
    estimate_dev_hours = 120
    estimate_qa_hours = 30
    estimate_opo_hours = 20
    opo_analyst_ratio = 0.5


class FakeAlloc:
    def __init__(self, override=None):
        self.override_estimate_analyst_hours = override["a"] if override else None
        self.override_estimate_dev_hours = override["d"] if override else None
        self.override_estimate_qa_hours = override["q"] if override else None
        self.override_estimate_opo_hours = override["o"] if override else None
        self.backlog_item = FakeBI()


def test_demand_from_override_when_set():
    alloc = FakeAlloc(override={"a": 25, "d": 80, "q": 40, "o": 20})
    demand = PlanningService.demand_by_role_from_allocation(alloc)
    # 25 + 20*0.5 = 35; 80 + 20*0.5 = 90; 40
    assert demand == {"analyst": 35.0, "dev": 90.0, "qa": 40.0}


def test_demand_from_jira_when_no_override():
    alloc = FakeAlloc()
    demand = PlanningService.demand_by_role_from_allocation(alloc)
    # 40 + 20*0.5 = 50; 120 + 20*0.5 = 130; 30
    assert demand == {"analyst": 50.0, "dev": 130.0, "qa": 30.0}


def test_skip_when_continuation_and_no_override():
    alloc = FakeAlloc()
    info_row = {"is_continuation": True, "spent_total": 80}
    assert should_skip_in_plan(alloc, info_row) is True


def test_no_skip_when_continuation_with_override():
    alloc = FakeAlloc(override={"a": 25, "d": 80, "q": 40, "o": 20})
    info_row = {"is_continuation": True, "spent_total": 80}
    assert should_skip_in_plan(alloc, info_row) is False


def test_no_skip_when_not_continuation():
    alloc = FakeAlloc()
    info_row = {"is_continuation": False, "spent_total": 0}
    assert should_skip_in_plan(alloc, info_row) is False


def test_no_skip_when_info_row_missing():
    alloc = FakeAlloc()
    assert should_skip_in_plan(alloc, None) is False
