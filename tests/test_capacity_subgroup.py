"""Ёмкость команды, разложенная по группам внутри неё."""

from datetime import date

import pytest

from app.models import (
    Category,
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    ProductionCalendarDay,
    RoleCapacityRule,
    Team,
    TeamSubgroup,
)
from app.services.capacity_service import CapacityService

TEAM = "Команда 1С (Бухгалтерия)"


@pytest.fixture
def productive_setup(db_session):
    """Правило 100% продуктива на Q2 2026 — иначе вся ёмкость нулевая."""
    wt = MandatoryWorkType(code="productive", label="Продуктив", is_active=True)
    db_session.add(wt)
    db_session.flush()
    db_session.add(
        Category(
            code="cat_productive", label="Productive", is_system=False, work_type_id=wt.id
        )
    )
    db_session.add(
        RoleCapacityRule(
            year=2026, quarter=2, role=None, work_type_id=wt.id, percent_of_norm=100.0
        )
    )
    db_session.flush()
    return wt


@pytest.fixture
def full_calendar_q2(db_session):
    """Q2 2026: в каждом месяце ровно 22 рабочих дня по 8 часов."""
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


def _seed_team(db_session, has_subgroups=True, name=TEAM):
    team = Team(name=name, has_subgroups=has_subgroups)
    db_session.add(team)
    db_session.flush()
    return team


def _dev(db_session, emp_id, account, team_name, subgroup_id=None):
    db_session.add(
        Employee(
            id=emp_id,
            display_name=emp_id,
            jira_account_id=account,
            is_active=True,
            role="dev",
        )
    )
    db_session.flush()
    db_session.add(
        EmployeeTeam(
            employee_id=emp_id,
            team=team_name,
            is_primary=True,
            subgroup_id=subgroup_id,
        )
    )


def test_capacity_splits_by_subgroup(db_session, productive_setup, full_calendar_q2):
    """Двое в разных группах — их часы не смешиваются."""
    team = _seed_team(db_session)
    calc = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    integ = TeamSubgroup(team_id=team.id, name="Интеграции", sort_order=2)
    db_session.add_all([calc, integ])
    db_session.flush()
    _dev(db_session, "e1", "a1", TEAM, calc.id)
    _dev(db_session, "e2", "a2", TEAM, integ.id)
    db_session.commit()

    out = CapacityService(db_session).team_role_capacity_by_subgroup(2026, 2, TEAM)

    assert set(out.keys()) == {calc.id, integ.id}
    assert out[calc.id]["dev"] == pytest.approx(528.0, abs=1.0)
    assert out[integ.id]["dev"] == pytest.approx(528.0, abs=1.0)


def test_sum_of_subgroups_equals_team_total(
    db_session, productive_setup, full_calendar_q2
):
    team = _seed_team(db_session)
    calc = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    integ = TeamSubgroup(team_id=team.id, name="Интеграции", sort_order=2)
    db_session.add_all([calc, integ])
    db_session.flush()
    _dev(db_session, "e1", "a1", TEAM, calc.id)
    _dev(db_session, "e2", "a2", TEAM, integ.id)
    db_session.commit()
    svc = CapacityService(db_session)

    by_group = svc.team_role_capacity_by_subgroup(2026, 2, TEAM)
    total = svc.team_role_capacity(2026, 2, team_filter=[TEAM])

    summed = sum(bucket["dev"] for bucket in by_group.values())
    assert summed == pytest.approx(total["dev"], abs=0.01)


def test_unassigned_employee_goes_to_none_bucket(
    db_session, productive_setup, full_calendar_q2
):
    team = _seed_team(db_session)
    calc = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    db_session.add(calc)
    db_session.flush()
    _dev(db_session, "e1", "a1", TEAM, calc.id)
    _dev(db_session, "e2", "a2", TEAM, None)
    db_session.commit()

    out = CapacityService(db_session).team_role_capacity_by_subgroup(2026, 2, TEAM)

    assert None in out
    assert out[None]["dev"] == pytest.approx(528.0, abs=1.0)


def test_team_without_subgroups_returns_empty(
    db_session, productive_setup, full_calendar_q2
):
    """Признак выключен — разреза нет, вызывающий код идёт общим путём."""
    _seed_team(db_session, has_subgroups=False, name="Команда без групп")
    _dev(db_session, "e1", "a1", "Команда без групп", None)
    db_session.commit()

    out = CapacityService(db_session).team_role_capacity_by_subgroup(
        2026, 2, "Команда без групп"
    )

    assert out == {}


def test_unknown_team_returns_empty(db_session):
    out = CapacityService(db_session).team_role_capacity_by_subgroup(
        2026, 2, "Нет такой команды"
    )

    assert out == {}
