"""Tests for PlanningService helpers: per-role demand + team capacity.

Жадный алгоритм `generate_scenario` удалён — сценарии формируются
вручную через `POST /planning/scenarios` + `PATCH allocations`.
"""

import pytest

from app.models import (
    BacklogItem,
    Category,
    Employee,
    MandatoryWorkType,
    RoleCapacityRule,
)
from app.services.planning_service import PlanningService


@pytest.fixture
def productive_setup(db_session):
    """Продуктивный вид работ с смэпленной категорией + 100% fallback."""
    wt = MandatoryWorkType(code="productive", label="Продуктив", is_active=True)
    db_session.add(wt)
    db_session.flush()
    db_session.add(
        Category(code="cat_productive", label="Productive", is_system=False,
                 work_type_id=wt.id)
    )
    db_session.add(
        RoleCapacityRule(year=2026, quarter=1, role=None,
                         work_type_id=wt.id, percent_of_norm=100.0)
    )
    db_session.flush()
    return wt


def test_team_capacity_hours_zero_without_employees(db_session):
    svc = PlanningService(db_session)
    assert svc._team_capacity_hours(2026, 1) == 0.0


def test_team_capacity_hours_sums_active_devs(db_session, productive_setup):
    a = Employee(jira_account_id="a1", display_name="A", is_active=True, role="dev")
    b = Employee(jira_account_id="b1", display_name="B", is_active=True, role="dev")
    db_session.add_all([a, b])
    db_session.flush()

    svc = PlanningService(db_session)
    # 2 × 512 ч (Q1 2026) = 1024
    assert svc._team_capacity_hours(2026, 1) == 1024.0


def test_demand_by_role_splits_opo():
    item = BacklogItem(
        title="x",
        estimate_analyst_hours=10,
        estimate_dev_hours=20,
        estimate_qa_hours=5,
        estimate_opo_hours=10,
        opo_analyst_ratio=0.6,
    )
    d = PlanningService._demand_by_role(item)
    assert d["analyst"] == pytest.approx(10 + 10 * 0.6)
    assert d["dev"] == pytest.approx(20 + 10 * 0.4)
    assert d["qa"] == 5


def test_demand_by_role_default_ratio_half():
    item = BacklogItem(title="x", estimate_opo_hours=10)
    d = PlanningService._demand_by_role(item)
    assert d["analyst"] == 5
    assert d["dev"] == 5
    assert d["qa"] == 0
