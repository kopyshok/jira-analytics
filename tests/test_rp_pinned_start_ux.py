"""TDD tests for explicit pinned_start flag in PATCH /assignments/{id}.

Semantics:
- PATCH with start_date (different from current) → pinned_start=True (implicit, drag compat).
- PATCH with pinned_start=False → unpins (regardless of start_date).
- PATCH with pinned_start=True (no start_date) → pins.
- POST split → parts have pinned_split=True, pinned_start=False.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import Base, get_db
from app.main import app
from app.models import BacklogItem, Employee, ResourcePlan, ResourcePlanAssignment
from app.models.employee_team import EmployeeTeam


@pytest.fixture
def client(testclient_db_session):
    def _get_db():
        yield testclient_db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def assignment(testclient_db_session):
    """Seed a minimal plan + single assignment. Returns (plan_id, assignment_id)."""
    db = testclient_db_session

    e = Employee(
        jira_account_id="pin-ux-e1",
        display_name="Pin Analyst",
        role="analyst",
        team="PIN_UX",
        is_active=True,
    )
    db.add(e)
    db.flush()
    db.add(EmployeeTeam(employee_id=e.id, team="PIN_UX", is_primary=True))
    db.flush()

    item = BacklogItem(
        title="pin-ux-item",
        estimate_analyst_hours=8.0,
        assignee_employee_id=e.id,
    )
    db.add(item)
    db.flush()

    plan = ResourcePlan(team="PIN_UX", quarter="Q2", year=2026, status="draft")
    db.add(plan)
    db.flush()

    a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="analyst",
        employee_id=e.id,
        part_number=1,
        hours_allocated=8.0,
        start_date=None,
        end_date=None,
        pinned_start=False,
    )
    db.add(a)
    db.commit()

    return plan.id, a.id


@pytest.fixture
def pinned_assignment(testclient_db_session):
    """Seed a plan + assignment that is already pinned_start=True."""
    db = testclient_db_session

    e = Employee(
        jira_account_id="pin-ux-e2",
        display_name="Pin Dev",
        role="developer",
        team="PIN_UX2",
        is_active=True,
    )
    db.add(e)
    db.flush()
    db.add(EmployeeTeam(employee_id=e.id, team="PIN_UX2", is_primary=True))
    db.flush()

    item = BacklogItem(
        title="pin-ux-item2",
        estimate_dev_hours=8.0,
        assignee_employee_id=e.id,
    )
    db.add(item)
    db.flush()

    plan = ResourcePlan(team="PIN_UX2", quarter="Q2", year=2026, status="draft")
    db.add(plan)
    db.flush()

    a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        employee_id=e.id,
        part_number=1,
        hours_allocated=8.0,
        start_date=None,
        end_date=None,
        pinned_start=True,
    )
    db.add(a)
    db.commit()

    return plan.id, a.id


@pytest.fixture
def splittable_assignment(testclient_db_session):
    """Seed an assignment that can be split (no pinned_split, has hours)."""
    db = testclient_db_session

    e = Employee(
        jira_account_id="pin-ux-e3",
        display_name="Split Dev",
        role="developer",
        team="PIN_UX3",
        is_active=True,
    )
    db.add(e)
    db.flush()
    db.add(EmployeeTeam(employee_id=e.id, team="PIN_UX3", is_primary=True))
    db.flush()

    from datetime import date
    item = BacklogItem(
        title="pin-ux-item3",
        estimate_dev_hours=16.0,
        assignee_employee_id=e.id,
    )
    db.add(item)
    db.flush()

    plan = ResourcePlan(team="PIN_UX3", quarter="Q2", year=2026, status="draft")
    db.add(plan)
    db.flush()

    a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        employee_id=e.id,
        part_number=1,
        hours_allocated=16.0,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 14),
        pinned_start=False,
        pinned_split=False,
    )
    db.add(a)
    db.commit()

    return plan.id, a.id


# ---------------------------------------------------------------------------


def test_patch_start_date_pins(client, assignment, testclient_db_session):
    """PATCH с новой start_date (без явного pinned_start) ставит pinned_start=True."""
    plan_id, assignment_id = assignment

    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{plan_id}/assignments/{assignment_id}",
        json={"start_date": "2026-04-15"},
    )
    assert r.status_code == 200, r.text

    db = testclient_db_session
    db.expire_all()
    a = db.get(ResourcePlanAssignment, assignment_id)
    assert a is not None
    assert a.pinned_start is True


def test_patch_pinned_start_false_unpins(client, pinned_assignment, testclient_db_session):
    """PATCH с явным pinned_start=False снимает фиксацию."""
    plan_id, assignment_id = pinned_assignment

    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{plan_id}/assignments/{assignment_id}",
        json={"pinned_start": False},
    )
    assert r.status_code == 200, r.text

    db = testclient_db_session
    db.expire_all()
    a = db.get(ResourcePlanAssignment, assignment_id)
    assert a is not None
    assert a.pinned_start is False


def test_patch_pinned_start_true_explicit(client, assignment, testclient_db_session):
    """PATCH с явным pinned_start=True (без start_date) ставит флаг."""
    plan_id, assignment_id = assignment

    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{plan_id}/assignments/{assignment_id}",
        json={"pinned_start": True},
    )
    assert r.status_code == 200, r.text

    db = testclient_db_session
    db.expire_all()
    a = db.get(ResourcePlanAssignment, assignment_id)
    assert a is not None
    assert a.pinned_start is True


def test_split_does_not_pin_start(client, splittable_assignment, testclient_db_session):
    """POST split возвращает parts с pinned_split=True, pinned_start=False."""
    plan_id, assignment_id = splittable_assignment

    r = client.post(
        f"/api/v1/resource-planning/resource-plans/{plan_id}/assignments/{assignment_id}/split",
        json={"parts": [8.0, 8.0], "cascade": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    parts = body["parts"]
    assert len(parts) == 2
    for p in parts:
        assert p["pinned_split"] is True
        assert p["pinned_start"] is False
