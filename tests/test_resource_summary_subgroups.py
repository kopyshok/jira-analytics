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
from tests.subgroup_fixtures import share

TEAM = "Команда 1С (Бухгалтерия)"
MONDAYS = (date(2026, 1, 5), date(2026, 1, 12), date(2026, 1, 19))


def _seed_calendar(db):
    for d in MONDAYS:
        db.add(
            ProductionCalendarDay(
                date=d, is_workday=True, kind="workday", hours=8.0, source="manual"
            )
        )


def _dev(db, eid, subgroup_id=None, role="dev", joined_at=None):
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
            employee_id=eid,
            team=TEAM,
            is_primary=True,
            joined_at=joined_at,
        )
    )
    if subgroup_id:
        db.add(share(eid, TEAM, subgroup_id))


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


def test_split_person_counts_by_share(db_session, two_groups):
    _dev(db_session, "e1")
    db_session.add(share("e1", TEAM, "sg-1", 60))
    db_session.add(share("e1", TEAM, "sg-2", 40))
    scenario = _scenario(db_session)
    db_session.commit()

    summary = ResourceBaseService(db_session).compute_summary(scenario)
    g1 = summary.gross_by_subgroup_role["sg-1"]["dev"]
    g2 = summary.gross_by_subgroup_role["sg-2"]["dev"]
    assert g1 == pytest.approx(summary.gross_by_role["dev"] * 0.6, abs=0.05)
    assert g1 + g2 == pytest.approx(summary.gross_by_role["dev"], abs=0.05)

    base = ResourceBaseService(db_session).compute(scenario)
    emp = base.employees[0]
    assert emp.subgroup_id is None
    assert set(emp.subgroup_hours) == {"sg-1", "sg-2"}
    assert emp.subgroup_labels == {"sg-1": "60%", "sg-2": "40%"}


def test_transfer_mid_quarter_splits_by_days(db_session, two_groups):
    _dev(db_session, "e1")
    db_session.add(share("e1", TEAM, "sg-1"))
    db_session.add(share("e1", TEAM, "sg-2", valid_from=date(2026, 2, 1)))
    scenario = _scenario(db_session)
    db_session.commit()

    base = ResourceBaseService(db_session).compute(scenario)
    emp = base.employees[0]
    jan = sum(d.hours for d in emp.days if d.date < date(2026, 2, 1))
    assert emp.subgroup_hours["sg-1"] == pytest.approx(jan, abs=0.05)
    assert emp.subgroup_hours["sg-1"] + emp.subgroup_hours["sg-2"] == pytest.approx(
        emp.total_hours, abs=0.05
    )
    assert emp.subgroup_labels == {"sg-1": "до 01.02", "sg-2": "с 01.02"}


def test_transfer_before_joining_shows_only_new_group(db_session, two_groups):
    """Пришёл в команду в день перевода — в квартале только новая группа, без «с 01.02»."""
    _dev(db_session, "e1", joined_at=date(2026, 2, 1))
    db_session.add(share("e1", TEAM, "sg-1"))
    db_session.add(share("e1", TEAM, "sg-2", valid_from=date(2026, 2, 1)))
    scenario = _scenario(db_session)
    db_session.commit()

    emp = ResourceBaseService(db_session).compute(scenario).employees[0]
    assert emp.subgroup_labels == {"sg-2": ""}
    assert set(emp.subgroup_hours) == {"sg-2"}
    assert emp.subgroup_hours["sg-2"] == pytest.approx(emp.total_hours, abs=0.05)
    assert emp.subgroup_id == "sg-2"


def test_ungrouped_when_holidays_precede_first_group_day(db_session, two_groups):
    """Праздники в начале квартала перед переводом: без правки ключ "" не
    попал бы в subgroup_hours (ни один рабочий день до перевода не пройден
    через split_hours), хотя первый день участия (01.01) ещё без группы.
    """
    for d in (date(2026, 1, 1), date(2026, 1, 2)):
        db_session.add(
            ProductionCalendarDay(
                date=d, is_workday=False, kind="holiday", hours=0.0, source="manual"
            )
        )
    _dev(db_session, "e1")
    db_session.add(share("e1", TEAM, "sg-1", valid_from=date(2026, 1, 5)))
    scenario = _scenario(db_session)
    db_session.commit()

    base = ResourceBaseService(db_session).compute(scenario)
    summary = ResourceBaseService(db_session).compute_summary(scenario)

    emp = base.employees[0]
    assert emp.subgroup_id is None
    assert "" in emp.subgroup_hours
    assert "e1" in [e["employee_id"] for e in summary.ungrouped_employees]


def test_ungrouped_employees_listed(db_session, two_groups):
    _dev(db_session, "e1", "sg-1")
    _dev(db_session, "e2")
    scenario = _scenario(db_session)
    db_session.commit()

    summary = ResourceBaseService(db_session).compute_summary(scenario)
    assert [e["employee_id"] for e in summary.ungrouped_employees] == ["e2"]


def test_role_outside_planning_left_out_of_every_total(db_session, two_groups):
    """Роль с выключенным «В планировании» не попадает ни в итоги по ролям,
    ни в разрез по группам — как и в карточке «Ресурс команды», иначе суммы
    расходятся (5534 против 5023)."""
    from app.models import Role

    db_session.add_all(
        [
            Role(code="dev", label="Программист", counts_in_planning=True),
            Role(code="other", label="Другое", counts_in_planning=False),
        ]
    )
    _dev(db_session, "e1", "sg-1")
    _dev(db_session, "e2", "sg-2", role="other")
    _dev(db_session, "e3", None, role="other")
    scenario = _scenario(db_session)
    db_session.flush()

    summary = ResourceBaseService(db_session).compute_summary(scenario)

    assert "other" not in summary.roles
    assert "other" not in summary.gross_by_role
    assert summary.gross_total == pytest.approx(summary.gross_by_role["dev"])
    assert summary.available_total == pytest.approx(summary.available_by_role["dev"])
    assert all("other" not in b for b in summary.gross_by_subgroup_role.values())
