"""KPI и Стол тимлида: витрины «на человека» режутся по его приписке к группе."""

from datetime import date

import pytest

from app.models import Employee, EmployeeTeam, Team, TeamSubgroup
from app.services.kpi.kpi_service import report_with_approvals
from app.services.subgroup_filter import NO_SUBGROUP_TOKEN, employee_ids

TEAM = "Команда 1С (Бухгалтерия)"


@pytest.fixture
def people(db_session):
    team = Team(name=TEAM, has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    calc = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    integ = TeamSubgroup(team_id=team.id, name="Интеграции", sort_order=2)
    db_session.add_all([calc, integ])
    db_session.flush()

    made = {}
    for code, name, group in [
        ("a", "Алексеев", calc),
        ("b", "Борисов", integ),
        ("c", "Сидоров", None),
    ]:
        emp = Employee(
            jira_account_id=f"acc-{code}", display_name=name, is_active=True, role="dev"
        )
        db_session.add(emp)
        db_session.flush()
        db_session.add(
            EmployeeTeam(
                employee_id=emp.id, team=TEAM, is_primary=True,
                subgroup_id=group.id if group else None,
                joined_at=date(2020, 1, 1),
            )
        )
        made[code] = emp
    db_session.commit()
    return {"calc": calc, "integ": integ, **made}


def test_group_split_covers_whole_team(db_session, people):
    """Сумма составов групп плюс «Без группы» — весь состав команды."""
    calc = employee_ids(db_session, [people["calc"].id], [TEAM])
    integ = employee_ids(db_session, [people["integ"].id], [TEAM])
    loose = employee_ids(db_session, [NO_SUBGROUP_TOKEN], [TEAM])

    assert calc == {people["a"].id}
    assert integ == {people["b"].id}
    assert loose == {people["c"].id}
    assert calc | integ | loose == {people[c].id for c in "abc"}


def test_kpi_report_narrowed_by_employee_group(db_session, people):
    whole = report_with_approvals(db_session, [TEAM], 2026, 8)
    only_calc = report_with_approvals(
        db_session, [TEAM], 2026, 8, subgroups=[people["calc"].id]
    )

    whole_ids = {r["employee_id"] for r in whole["rows"]} | {
        s["employee_id"] for s in whole["skipped"]
    }
    calc_ids = {r["employee_id"] for r in only_calc["rows"]} | {
        s["employee_id"] for s in only_calc["skipped"]
    }

    assert whole_ids >= calc_ids
    assert calc_ids <= {people["a"].id}
    assert people["b"].id not in calc_ids


def test_empty_filter_leaves_report_untouched(db_session, people):
    a = report_with_approvals(db_session, [TEAM], 2026, 8)
    b = report_with_approvals(db_session, [TEAM], 2026, 8, subgroups=[])

    assert a == b
