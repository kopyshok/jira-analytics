"""Разрез ресурса сценария по группам внутри команды."""

from datetime import date

import pytest

from app.models import (
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    PlanningScenario,
    ProductionCalendarDay,
    ScenarioRule,
    Team,
    TeamSubgroup,
)
from app.services.resource_base_service import ResourceBaseService

TEAM = "Команда 1С (Бухгалтерия)"
MONDAYS = (date(2026, 1, 5), date(2026, 1, 12), date(2026, 1, 19))


def _seed_calendar(db):
    for d in MONDAYS:
        db.add(
            ProductionCalendarDay(
                date=d, is_workday=True, kind="workday", hours=8.0, source="manual"
            )
        )


def _dev(db, eid, subgroup_id=None, role="dev"):
    db.add(
        Employee(
            id=eid,
            jira_account_id=f"jira-{eid}",
            display_name=f"Employee {eid}",
            role=role,
            is_active=True,
        )
    )
    db.add(
        EmployeeTeam(
            employee_id=eid, team=TEAM, is_primary=True, subgroup_id=subgroup_id
        )
    )


def _scenario(db, sid="sc-1", external_qa=None):
    s = PlanningScenario(
        id=sid,
        name="Test",
        quarter="Q1",
        year=2026,
        team=TEAM,
        status="draft",
        external_qa_hours=external_qa,
    )
    db.add(s)
    return s


@pytest.fixture
def two_groups(db_session):
    team = Team(id="t-1", name=TEAM, has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    db_session.add_all(
        [
            TeamSubgroup(id="sg-1", team_id="t-1", name="Расчёты", sort_order=1),
            TeamSubgroup(id="sg-2", team_id="t-1", name="Интеграции", sort_order=2),
        ]
    )
    _seed_calendar(db_session)
    db_session.flush()
    return team


def test_breakdown_splits_hours_between_groups(db_session, two_groups):
    _dev(db_session, "e1", "sg-1")
    _dev(db_session, "e2", "sg-2")
    scenario = _scenario(db_session)
    db_session.flush()

    summary = ResourceBaseService(db_session).compute_summary(scenario)

    assert [g["name"] for g in summary.subgroups] == ["Расчёты", "Интеграции"]
    half = summary.gross_by_role["dev"] / 2
    assert summary.gross_by_subgroup_role["sg-1"]["dev"] == pytest.approx(half)
    assert summary.gross_by_subgroup_role["sg-2"]["dev"] == pytest.approx(half)


def test_sum_over_groups_equals_team_total(db_session, two_groups):
    """Суммы по группам сходятся с итогом по команде — и до вычетов, и после."""
    _dev(db_session, "e1", "sg-1")
    _dev(db_session, "e2", "sg-2")
    _dev(db_session, "e3", None)
    wt = MandatoryWorkType(
        id="wt-1", code="wt_1", label="Совещания", is_active=True, subtracts_from_pool=True
    )
    db_session.add(wt)
    scenario = _scenario(db_session)
    db_session.flush()
    db_session.add(
        ScenarioRule(
            scenario_id=scenario.id, work_type_id="wt-1", role=None, percent_of_norm=25.0
        )
    )
    db_session.flush()

    summary = ResourceBaseService(db_session).compute_summary(scenario)

    gross = sum(b.get("dev", 0.0) for b in summary.gross_by_subgroup_role.values())
    available = sum(
        b.get("dev", 0.0) for b in summary.available_by_subgroup_role.values()
    )
    assert gross == pytest.approx(summary.gross_by_role["dev"], abs=0.01)
    assert available == pytest.approx(summary.available_by_role["dev"], abs=0.05)


def test_employee_without_group_lands_in_empty_key(db_session, two_groups):
    _dev(db_session, "e1", None)
    scenario = _scenario(db_session)
    db_session.flush()

    summary = ResourceBaseService(db_session).compute_summary(scenario)

    assert "" in summary.gross_by_subgroup_role
    assert summary.gross_by_subgroup_role[""]["dev"] == pytest.approx(
        summary.gross_by_role["dev"]
    )


def test_team_without_subgroups_has_empty_breakdown(db_session):
    """Признак выключен — разреза нет, сценарий выглядит как до правки."""
    db_session.add(Team(id="t-2", name=TEAM, has_subgroups=False))
    _seed_calendar(db_session)
    _dev(db_session, "e1", None)
    scenario = _scenario(db_session)
    db_session.flush()

    summary = ResourceBaseService(db_session).compute_summary(scenario)

    assert summary.subgroups == []
    assert summary.gross_by_subgroup_role == {}
    assert summary.available_by_subgroup_role == {}


def test_external_qa_stays_out_of_groups(db_session, two_groups):
    """Внешний QA задан на всю команду и группе не принадлежит."""
    _dev(db_session, "e1", "sg-1", role="qa")
    scenario = _scenario(db_session, external_qa=100.0)
    db_session.flush()

    summary = ResourceBaseService(db_session).compute_summary(scenario)

    assert all("qa" not in b for b in summary.gross_by_subgroup_role.values())
