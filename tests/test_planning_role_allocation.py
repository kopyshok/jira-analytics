"""PlanningService.generate_scenario allocates backlog items respecting per-role
capacity; ОПЭ hours split via opo_analyst_ratio."""

from datetime import date

import pytest

from app.models import (
    BacklogItem,
    Category,
    Employee,
    MandatoryWorkType,
    ProductionCalendarDay,
    RoleCapacityRule,
)
from app.services.planning_service import PlanningService


@pytest.fixture
def productive_setup(db_session):
    """v3 baseline: productive work type + linked category + 100% fallback rule."""
    wt = MandatoryWorkType(
        code="productive", label="Продуктив", is_active=True
    )
    db_session.add(wt)
    db_session.flush()
    db_session.add(
        Category(
            code="cat_productive",
            label="Productive",
            is_system=False,
            work_type_id=wt.id,
        )
    )
    db_session.add(
        RoleCapacityRule(
            year=2026,
            quarter=2,
            role=None,
            work_type_id=wt.id,
            percent_of_norm=100.0,
        )
    )
    db_session.flush()
    return wt


@pytest.fixture
def q2_calendar(db_session):
    """Seed Q2 2026: 22 workdays × 8h = 176h per month."""
    from calendar import monthrange

    for m in (4, 5, 6):
        last = monthrange(2026, m)[1]
        for d in range(1, last + 1):
            is_wd = d <= 22
            db_session.add(
                ProductionCalendarDay(
                    date=date(2026, m, d),
                    is_workday=is_wd,
                    kind="workday" if is_wd else "holiday",
                    hours=8.0 if is_wd else 0.0,
                )
            )
    db_session.commit()


@pytest.fixture
def three_roles(db_session):
    """One employee per role (analyst/dev/qa) → each gets 528h capacity for Q2."""
    db_session.add_all(
        [
            Employee(
                id="e1",
                display_name="A",
                jira_account_id="a1",
                is_active=True,
                role="analyst",
            ),
            Employee(
                id="e2",
                display_name="D",
                jira_account_id="a2",
                is_active=True,
                role="dev",
            ),
            Employee(
                id="e3",
                display_name="Q",
                jira_account_id="a3",
                is_active=True,
                role="qa",
            ),
        ]
    )
    db_session.flush()


def _alloc_by_id(result):
    return {a.backlog_item_id: a for a in result.allocations}


def test_allocation_includes_items_when_all_roles_fit(
    db_session, productive_setup, q2_calendar, three_roles
):
    # 3 items; all fit (analyst 400 ≤ 528, dev 400 ≤ 528, qa 300 ≤ 528 after b1+b2+b3)
    db_session.add_all(
        [
            BacklogItem(
                id="b1",
                title="T1",
                year=2026,
                quarter="Q2",
                priority=1,
                estimate_analyst_hours=200,
                estimate_dev_hours=200,
                estimate_qa_hours=100,
                estimate_opo_hours=0,
                estimate_hours=500,
            ),
            BacklogItem(
                id="b2",
                title="T2",
                year=2026,
                quarter="Q2",
                priority=2,
                estimate_analyst_hours=200,
                estimate_dev_hours=200,
                estimate_qa_hours=200,
                estimate_opo_hours=0,
                estimate_hours=600,
            ),
            BacklogItem(
                id="b3",
                title="T3",
                year=2026,
                quarter="Q2",
                priority=3,
                estimate_analyst_hours=50,
                estimate_dev_hours=50,
                estimate_qa_hours=50,
                estimate_opo_hours=0,
                estimate_hours=150,
            ),
        ]
    )
    db_session.commit()

    result = PlanningService(db_session).generate_scenario(
        name="Q2 draft", year=2026, quarter=2
    )
    a = _alloc_by_id(result)
    assert a["b1"].included is True
    assert a["b2"].included is True
    assert a["b3"].included is True


def test_allocation_rejects_item_when_any_role_overcapacity(
    db_session, productive_setup, q2_calendar, three_roles
):
    # b1 fits (qa=500 ≤ 528). b2 needs qa=100 but only 28 remain → skipped.
    db_session.add_all(
        [
            BacklogItem(
                id="b1",
                title="T1",
                year=2026,
                quarter="Q2",
                priority=1,
                estimate_analyst_hours=100,
                estimate_dev_hours=100,
                estimate_qa_hours=500,
                estimate_opo_hours=0,
                estimate_hours=700,
            ),
            BacklogItem(
                id="b2",
                title="T2",
                year=2026,
                quarter="Q2",
                priority=2,
                estimate_analyst_hours=50,
                estimate_dev_hours=50,
                estimate_qa_hours=100,
                estimate_opo_hours=0,
                estimate_hours=200,
            ),
        ]
    )
    db_session.commit()

    result = PlanningService(db_session).generate_scenario(
        name="Q2 draft", year=2026, quarter=2
    )
    a = _alloc_by_id(result)
    assert a["b1"].included is True
    assert a["b2"].included is False
    assert a["b2"].reason == "no_capacity_left"


def test_opo_hours_split_between_analyst_and_dev(
    db_session, productive_setup, q2_calendar, three_roles
):
    # opo=100, ratio=0.7 → analyst demand = 400+70 = 470 ≤ 528, dev = 400+30 = 430 ≤ 528
    db_session.add_all(
        [
            BacklogItem(
                id="b1",
                title="T1",
                year=2026,
                quarter="Q2",
                priority=1,
                estimate_analyst_hours=400,
                estimate_dev_hours=400,
                estimate_qa_hours=100,
                estimate_opo_hours=100,
                opo_analyst_ratio=0.7,
                estimate_hours=1000,
            ),
        ]
    )
    db_session.commit()

    result = PlanningService(db_session).generate_scenario(
        name="Q2 draft", year=2026, quarter=2
    )
    a = _alloc_by_id(result)
    assert a["b1"].included is True


def test_opo_split_can_reject_when_analyst_overflows(
    db_session, productive_setup, q2_calendar, three_roles
):
    # opo=200, ratio=0.9 → analyst = 400 + 180 = 580 > 528 → reject
    db_session.add_all(
        [
            BacklogItem(
                id="b1",
                title="T1",
                year=2026,
                quarter="Q2",
                priority=1,
                estimate_analyst_hours=400,
                estimate_dev_hours=300,
                estimate_qa_hours=100,
                estimate_opo_hours=200,
                opo_analyst_ratio=0.9,
                estimate_hours=1000,
            ),
        ]
    )
    db_session.commit()

    result = PlanningService(db_session).generate_scenario(
        name="Q2 draft", year=2026, quarter=2
    )
    a = _alloc_by_id(result)
    assert a["b1"].included is False


def test_opo_default_ratio_is_half_when_null(
    db_session, productive_setup, q2_calendar, three_roles
):
    # opo_analyst_ratio=None → defaults to 0.5
    # analyst = 400 + 100*0.5 = 450 ≤ 528, dev = 400 + 100*0.5 = 450 ≤ 528 OK
    db_session.add_all(
        [
            BacklogItem(
                id="b1",
                title="T1",
                year=2026,
                quarter="Q2",
                priority=1,
                estimate_analyst_hours=400,
                estimate_dev_hours=400,
                estimate_qa_hours=100,
                estimate_opo_hours=100,
                opo_analyst_ratio=None,
                estimate_hours=1000,
            ),
        ]
    )
    db_session.commit()

    result = PlanningService(db_session).generate_scenario(
        name="Q2 draft", year=2026, quarter=2
    )
    a = _alloc_by_id(result)
    assert a["b1"].included is True
