"""Общий фильтр по группам: пустой вход не меняет ни один запрос."""

import pytest

from app.models import Employee, EmployeeTeam, Team, TeamSubgroup
from app.services import subgroup_filter as sf

TEAM = "Команда 1С (Бухгалтерия)"


@pytest.fixture
def groups(db_session):
    team = Team(name=TEAM, has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    calc = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    integ = TeamSubgroup(team_id=team.id, name="Интеграции", sort_order=2)
    db_session.add_all([calc, integ])
    emp = Employee(jira_account_id="acc-1", display_name="Иванов")
    other = Employee(jira_account_id="acc-2", display_name="Петров")
    db_session.add_all([emp, other])
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True, subgroup_id=calc.id),
        EmployeeTeam(employee_id=other.id, team=TEAM, is_primary=True, subgroup_id=integ.id),
    ])
    db_session.commit()
    return {"calc": calc, "integ": integ, "emp": emp, "other": other}


def test_parse():
    assert sf.parse_subgroups_csv(None) == []
    assert sf.parse_subgroups_csv("") == []
    assert sf.parse_subgroups_csv(" a , b ,, ") == ["a", "b"]


def test_empty_input_adds_nothing(db_session):
    assert sf.issue_clause([]) is None
    assert sf.employee_ids(db_session, []) is None
    assert sf.names(db_session, []) == {}


def test_employee_ids_by_assignment(db_session, groups):
    assert sf.employee_ids(db_session, [groups["calc"].id]) == {groups["emp"].id}
    assert sf.employee_ids(db_session, [groups["calc"].id, groups["integ"].id]) == {
        groups["emp"].id,
        groups["other"].id,
    }


def test_unknown_id_selects_nobody(db_session, groups):
    assert sf.employee_ids(db_session, ["нет-такой"]) == set()
    assert sf.names(db_session, ["нет-такой"]) == {}


def test_names(db_session, groups):
    assert sf.names(db_session, [groups["integ"].id]) == {
        groups["integ"].id: "Интеграции"
    }
