"""Тесты на pinned-флаги и manual_edit_at в ResourcePlanAssignment."""

from datetime import datetime

from app.models import ResourcePlanAssignment


def test_assignment_pinned_fields(db_session):
    a = ResourcePlanAssignment(
        plan_id="p1", backlog_item_id="b1", phase="analyst",
        pinned_start=True, pinned_employee=False, pinned_split=True,
        manual_edit_at=datetime(2026, 5, 10, 12, 0),
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    assert a.pinned_start is True
    assert a.pinned_employee is False
    assert a.pinned_split is True
    assert a.manual_edit_at.year == 2026


def test_is_pinned_backcompat_property(db_session):
    """Backward-compat property: True if any pin flag set."""
    a = ResourcePlanAssignment(
        plan_id="p1", backlog_item_id="b1", phase="dev",
        pinned_start=False, pinned_employee=False, pinned_split=False,
    )
    assert a.is_pinned is False
    a.pinned_start = True
    assert a.is_pinned is True
