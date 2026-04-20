"""team_role_capacity groups available hours by Employee.role."""

from datetime import date

import pytest

from app.models import (
    Category,
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    ProductionCalendarDay,
    RoleCapacityRule,
)
from app.services.capacity_service import CapacityService


@pytest.fixture
def productive_setup(db_session):
    """v3 baseline: productive work type + linked category + 100% fallback rule.

    Без этого `productive_percent = 0` → `available_hours = 0`, и тесты
    `team_role_capacity` всегда будут получать нули. Правило `role=None`
    задаёт fallback 100% для всех сотрудников на Q2 2026.
    """
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
def full_calendar_q2(db_session):
    """Seed Q2 2026 calendar so every month has exactly 22 workdays × 8h = 176h.

    Days 1..22 are workdays (hours=8), days 23..31 are explicitly non-workdays
    (hours=0). Без явных строк для 23..31 сервис применил бы weekday-fallback и
    число рабочих дней оказалось бы нестабильным.
    """
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


def test_role_capacity_groups_by_employee_role(
    db_session, productive_setup, full_calendar_q2
):
    db_session.add_all(
        [
            Employee(
                id="e1",
                display_name="A1",
                jira_account_id="a1",
                is_active=True,
                role="analyst",
            ),
            Employee(
                id="e2",
                display_name="D1",
                jira_account_id="a2",
                is_active=True,
                role="dev",
            ),
            Employee(
                id="e3",
                display_name="D2",
                jira_account_id="a3",
                is_active=True,
                role="dev",
            ),
            Employee(
                id="e4",
                display_name="Q1",
                jira_account_id="a4",
                is_active=True,
                role="qa",
            ),
        ]
    )
    db_session.commit()

    svc = CapacityService(db_session)
    caps = svc.team_role_capacity(year=2026, quarter=2)
    # Each employee: 3 months × 22 days × 8h = 528h raw, no absences, 100% productive
    assert caps["analyst"] == pytest.approx(528.0, abs=1.0)
    assert caps["dev"] == pytest.approx(1056.0, abs=1.0)
    assert caps["qa"] == pytest.approx(528.0, abs=1.0)


def test_role_capacity_skips_unknown_role(
    db_session, productive_setup, full_calendar_q2
):
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
                id="e5",
                display_name="PM",
                jira_account_id="a5",
                is_active=True,
                role="manager",
            ),
            Employee(
                id="e6",
                display_name="X",
                jira_account_id="a6",
                is_active=True,
                role=None,
            ),
        ]
    )
    db_session.commit()

    svc = CapacityService(db_session)
    caps = svc.team_role_capacity(year=2026, quarter=2)
    assert caps["analyst"] == pytest.approx(528.0, abs=1.0)
    assert caps["dev"] == 0
    assert caps["qa"] == 0


def test_role_capacity_respects_team_filter(
    db_session, productive_setup, full_calendar_q2
):
    e1 = Employee(
        id="e1",
        display_name="A",
        jira_account_id="a1",
        is_active=True,
        role="analyst",
    )
    e2 = Employee(
        id="e2",
        display_name="B",
        jira_account_id="a2",
        is_active=True,
        role="analyst",
    )
    db_session.add_all(
        [
            e1,
            e2,
            EmployeeTeam(id="t1", employee_id="e1", team="Alpha", is_primary=True),
            EmployeeTeam(id="t2", employee_id="e2", team="Beta", is_primary=True),
        ]
    )
    db_session.commit()

    svc = CapacityService(db_session)
    caps = svc.team_role_capacity(year=2026, quarter=2, team_filter=["Alpha"])
    assert caps["analyst"] == pytest.approx(528.0, abs=1.0)


def test_role_capacity_no_duplicate_when_employee_has_multiple_teams(
    db_session, productive_setup, full_calendar_q2
):
    """Employee with two EmployeeTeam rows matched by team_filter must count once."""
    e1 = Employee(
        id="e1",
        display_name="Multi",
        jira_account_id="a1",
        is_active=True,
        role="analyst",
    )
    db_session.add_all(
        [
            e1,
            EmployeeTeam(
                id="t1", employee_id="e1", team="Alpha", is_primary=True
            ),
            EmployeeTeam(
                id="t2", employee_id="e1", team="Beta", is_primary=False
            ),
        ]
    )
    db_session.commit()

    svc = CapacityService(db_session)
    caps = svc.team_role_capacity(
        year=2026, quarter=2, team_filter=["Alpha", "Beta"]
    )
    # One employee × 528h — must not be double-counted via JOIN.
    assert caps["analyst"] == pytest.approx(528.0, abs=1.0)
