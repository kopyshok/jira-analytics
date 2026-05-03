"""Tests for ResourcePlanningService."""

from datetime import date
from unittest.mock import MagicMock

from app.services.resource_planning_service import (
    DEFAULT_HOURS_PER_DAY,
    PHASE_HOURS_FIELD,
    PHASE_ORDER,
    ResourcePlanningService,
)


def test_phase_order_correct():
    """Phase order must be analyst→dev→qa→opo."""
    assert PHASE_ORDER == ["analyst", "dev", "qa", "opo"]


def test_phase_hours_fields_mapped():
    """All phases have a corresponding BacklogItem field."""
    assert PHASE_HOURS_FIELD["analyst"] == "estimate_analyst_hours"
    assert PHASE_HOURS_FIELD["dev"] == "estimate_dev_hours"
    assert PHASE_HOURS_FIELD["qa"] == "estimate_qa_hours"
    assert PHASE_HOURS_FIELD["opo"] == "estimate_opo_hours"


def test_block_targets_employee_specific():
    """Block with employee_id only targets that employee."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    block = MagicMock()
    block.employee_id = "emp-1"
    block.role_id = None
    block.team = None

    emp1 = MagicMock()
    emp1.id = "emp-1"
    emp1.role = "analyst"
    emp1.team = "T1"
    emp2 = MagicMock()
    emp2.id = "emp-2"
    emp2.role = "analyst"
    emp2.team = "T1"

    result = svc._block_targets(block, [emp1, emp2], {})
    assert result == ["emp-1"]


def test_block_targets_role():
    """Block with role_id targets all employees of that role."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    block = MagicMock()
    block.employee_id = None
    block.role_id = "role-uuid-analyst"
    block.team = None

    emp1 = MagicMock()
    emp1.id = "emp-1"
    emp1.role = "analyst"
    emp2 = MagicMock()
    emp2.id = "emp-2"
    emp2.role = "dev"

    # role_id → role_code mapping
    role_id_to_code = {"role-uuid-analyst": "analyst"}

    result = svc._block_targets(block, [emp1, emp2], role_id_to_code)
    assert "emp-1" in result
    assert "emp-2" not in result


def test_allocate_hours_simple():
    """Basic allocation: 12 hours over 2 days of 6h each."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    emp_id = "emp-1"
    remaining = {
        emp_id: {
            date(2026, 4, 1): 6.0,
            date(2026, 4, 2): 6.0,
            date(2026, 4, 3): 6.0,
        }
    }

    segments = svc._allocate_hours(
        emp_id, 12.0, date(2026, 4, 1), date(2026, 4, 30), remaining
    )

    assert len(segments) == 1
    seg_start, seg_end, seg_hours, part_num = segments[0]
    assert seg_start == date(2026, 4, 1)
    assert seg_end == date(2026, 4, 2)
    assert abs(seg_hours - 12.0) < 0.01
    assert part_num == 1
    # Remaining hours consumed
    assert remaining[emp_id][date(2026, 4, 1)] == 0.0
    assert remaining[emp_id][date(2026, 4, 2)] == 0.0


def test_allocate_hours_split_on_gap():
    """Creates two segments when there's a 0-availability gap mid-work."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    emp_id = "emp-1"
    remaining = {
        emp_id: {
            date(2026, 4, 1): 6.0,
            date(2026, 4, 2): 6.0,
            date(2026, 4, 3): 0.0,  # blocked
            date(2026, 4, 4): 0.0,  # blocked
            date(2026, 4, 5): 0.0,  # weekend
            date(2026, 4, 6): 0.0,  # weekend
            date(2026, 4, 7): 6.0,
        }
    }

    segments = svc._allocate_hours(
        emp_id, 18.0, date(2026, 4, 1), date(2026, 4, 30), remaining
    )

    # Should produce 2 segments: [Apr1-2] and [Apr7]
    assert len(segments) == 2
    assert segments[0][0] == date(2026, 4, 1)
    assert segments[0][1] == date(2026, 4, 2)
    assert segments[0][3] == 1  # part_number
    assert segments[1][0] == date(2026, 4, 7)
    assert segments[1][3] == 2  # part_number
