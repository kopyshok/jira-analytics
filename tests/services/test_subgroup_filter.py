"""Общий фильтр по группам: пустой вход не меняет ни один запрос."""

from datetime import date

import pytest

from app.models import Employee, EmployeeTeam, Team, TeamSubgroup
from app.services import subgroup_filter as sf
from tests.subgroup_fixtures import share

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
    db_session.add_all([
        share(emp.id, TEAM, calc.id),
        share(other.id, TEAM, integ.id),
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


def test_no_subgroup_token_picks_unassigned(db_session, groups):
    """«Без группы» — сотрудники команды, которых не приписали."""
    from app.models import Employee, EmployeeTeam

    loose = Employee(jira_account_id="acc-3", display_name="Сидоров")
    db_session.add(loose)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=loose.id, team=TEAM, is_primary=True))
    db_session.commit()

    got = sf.employee_ids(db_session, [sf.NO_SUBGROUP_TOKEN], teams=[TEAM])

    assert got == {loose.id}
    assert sf.names(db_session, [sf.NO_SUBGROUP_TOKEN]) == {
        sf.NO_SUBGROUP_TOKEN: "Без группы"
    }


# --- Распределение за период ----------------------------------------------

NOV_1, NOV_30 = date(2026, 11, 1), date(2026, 11, 30)


def _member(db_session, name, *shares, **membership):
    """Участник команды с записями распределения ``(группа, процент, с даты)``."""
    emp = Employee(jira_account_id=f"acc-{name}", display_name=name)
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True, **membership))
    for grp, percent, valid_from in shares:
        db_session.add(share(emp.id, TEAM, grp.id, percent, valid_from))
    db_session.commit()
    return emp


def test_transferred_matches_new_group_only_after_date(db_session, groups):
    moved = _member(
        db_session, "moved",
        (groups["calc"], 100, None),
        (groups["integ"], 100, date(2026, 11, 15)),
    )
    integ = [groups["integ"].id]

    assert moved.id in sf.employee_ids(db_session, integ, [TEAM], NOV_1, NOV_30)
    assert moved.id not in sf.employee_ids(
        db_session, integ, [TEAM], NOV_1, date(2026, 11, 14)
    )
    assert moved.id in sf.employee_ids(
        db_session, [groups["calc"].id], [TEAM], NOV_1, NOV_30
    )


def test_shared_matches_both_groups(db_session, groups):
    shared = _member(
        db_session, "shared",
        (groups["calc"], 60, None),
        (groups["integ"], 40, None),
    )

    for gid in (groups["calc"].id, groups["integ"].id):
        assert shared.id in sf.employee_ids(db_session, [gid], [TEAM], NOV_1, NOV_30)


def test_share_after_leaving_does_not_match(db_session, groups):
    """Запись, начавшаяся после выхода из команды, в период не попадает."""
    left = _member(
        db_session, "left",
        (groups["calc"], 100, None),
        (groups["integ"], 100, date(2026, 11, 15)),
        left_at=date(2026, 11, 10),
    )

    assert left.id not in sf.employee_ids(
        db_session, [groups["integ"].id], [TEAM], NOV_1, NOV_30
    )
    assert left.id in sf.employee_ids(
        db_session, [groups["calc"].id], [TEAM], NOV_1, NOV_30
    )


def test_inverted_period_behaves_as_single_day_at_start(db_session, groups):
    """Перевёрнутый период (конец раньше начала) сужается до дня начала."""
    moved = _member(
        db_session, "moved",
        (groups["calc"], 100, None),
        (groups["integ"], 100, date(2026, 11, 15)),
    )

    normal = sf.employee_ids(
        db_session, [groups["integ"].id], [TEAM], date(2026, 11, 20), date(2026, 11, 20)
    )
    inverted = sf.employee_ids(
        db_session, [groups["integ"].id], [TEAM], date(2026, 11, 20), date(2026, 11, 1)
    )

    assert inverted == normal
    assert moved.id in inverted


def test_no_subgroup_token_includes_late_first_record(db_session, groups):
    """«Без группы» — и неприписанный, и тот, чья первая запись начинается позже начала периода."""
    loose = _member(db_session, "loose")
    late = _member(db_session, "late", (groups["integ"], 100, date(2026, 11, 15)))

    got = sf.employee_ids(db_session, [sf.NO_SUBGROUP_TOKEN], [TEAM], NOV_1, NOV_30)

    assert got == {loose.id, late.id}
