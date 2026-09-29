"""Переток внутри команды: чей ресурс ушёл к соседям."""

from datetime import date, datetime

import pytest

from app.models import (
    Employee,
    EmployeeTeam,
    Issue,
    Project,
    Team,
    TeamSubgroup,
    Worklog,
)
from app.services.subgroup_flow_service import flow_for_team
from app.services.subgroup_resolver import SubgroupResolver
from tests.subgroup_fixtures import share

TEAM = "Команда 1С (Бухгалтерия)"
OTHER_TEAM = "Команда 2"
DAY = datetime(2026, 8, 5, 10, 0)
FROM, TO = date(2026, 7, 1), date(2026, 9, 30)


@pytest.fixture
def data(db_session):
    db_session.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    team = Team(name=TEAM, has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    calc = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    integ = TeamSubgroup(team_id=team.id, name="Интеграции", sort_order=2)
    db_session.add_all([calc, integ])
    db_session.flush()

    a = Employee(jira_account_id="acc-a", display_name="Алексеев", is_active=True)
    b = Employee(jira_account_id="acc-b", display_name="Борисов", is_active=True)
    alien = Employee(jira_account_id="acc-x", display_name="Чужаков", is_active=True)
    db_session.add_all([a, b, alien])
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(employee_id=a.id, team=TEAM, is_primary=True),
        EmployeeTeam(employee_id=b.id, team=TEAM, is_primary=True),
        EmployeeTeam(employee_id=alien.id, team=OTHER_TEAM, is_primary=True),
    ])
    db_session.add_all([
        share(a.id, TEAM, calc.id),
        share(b.id, TEAM, integ.id),
    ])

    def issue(key, subgroup):
        it = Issue(
            jira_issue_id=key, key=key, summary=key, issue_type="Task",
            status="Open", project_id="p1", team=TEAM,
            assigned_subgroup_id=subgroup.id,
        )
        db_session.add(it)
        db_session.flush()
        return it

    calc_issue = issue("OS-1", calc)
    integ_issue = issue("OS-2", integ)

    db_session.add_all([
        # своя работа
        Worklog(jira_worklog_id="w0", issue_id=calc_issue.id, employee_id=a.id,
                started_at=DAY, time_spent_seconds=5 * 3600, hours=5.0),
        # переток: человек «Расчётов» на задаче «Интеграций»
        Worklog(jira_worklog_id="w1", issue_id=integ_issue.id, employee_id=a.id,
                started_at=DAY, time_spent_seconds=3 * 3600, hours=3.0),
        # помощь извне: чужая команда, перетоком не считается
        Worklog(jira_worklog_id="w2", issue_id=integ_issue.id, employee_id=alien.id,
                started_at=DAY, time_spent_seconds=7 * 3600, hours=7.0),
    ])
    db_session.commit()
    SubgroupResolver(db_session).recompute_effective()
    return {"team": team, "calc": calc, "integ": integ}


def test_flow_counts_both_directions(db_session, data):
    rows = {r.subgroup_id: r for r in flow_for_team(db_session, TEAM, FROM, TO)}

    assert rows[data["calc"].id].out_hours == 3.0
    assert rows[data["calc"].id].in_hours == 0.0
    assert rows[data["integ"].id].in_hours == 3.0
    assert rows[data["integ"].id].out_hours == 0.0


def test_alien_help_is_not_flow(db_session, data):
    """Часы чужой команды — помощь извне, в переток не попадают."""
    total_in = sum(r.in_hours for r in flow_for_team(db_session, TEAM, FROM, TO))

    assert total_in == 3.0  # 7 часов чужака сюда не вошли


def test_team_without_flag_returns_nothing(db_session, data):
    data["team"].has_subgroups = False
    db_session.commit()
    SubgroupResolver(db_session).recompute_effective()

    assert flow_for_team(db_session, TEAM, FROM, TO) == []


# --- Группа человека на дату списания -------------------------------------

Q4_FROM, Q4_TO = date(2026, 10, 1), date(2026, 12, 31)


@pytest.fixture
def three(db_session):
    """Команда с тремя группами и задачей в каждой."""
    db_session.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    team = Team(name=TEAM, has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    groups = {
        code: TeamSubgroup(team_id=team.id, name=code, sort_order=i)
        for i, code in enumerate("ABC", start=1)
    }
    db_session.add_all(groups.values())
    db_session.flush()
    issues = {}
    for code, grp in groups.items():
        it = Issue(
            jira_issue_id=f"OS-{code}", key=f"OS-{code}", summary=code,
            issue_type="Task", status="Open", project_id="p1", team=TEAM,
            assigned_subgroup_id=grp.id,
        )
        db_session.add(it)
        issues[code] = it
    db_session.commit()
    return {"groups": groups, "issues": issues}


def _person(db_session, account_id, *shares, **membership):
    emp = Employee(jira_account_id=account_id, display_name=account_id, is_active=True)
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True, **membership))
    for grp, percent, valid_from in shares:
        db_session.add(share(emp.id, TEAM, grp.id, percent, valid_from))
    db_session.flush()
    return emp


def _log(db_session, wid, issue, emp, day, hours):
    db_session.add(Worklog(
        jira_worklog_id=wid, issue_id=issue.id, employee_id=emp.id,
        started_at=datetime.combine(day, datetime.min.time()).replace(hour=10),
        time_spent_seconds=int(hours * 3600), hours=hours,
    ))


def _flow(db_session):
    db_session.commit()
    SubgroupResolver(db_session).recompute_effective()
    return {r.subgroup_name: r for r in flow_for_team(db_session, TEAM, Q4_FROM, Q4_TO)}


def test_transfer_flow_by_worklog_date(db_session, three):
    """До перевода работа в новой группе — переток, после — своя работа."""
    g, it = three["groups"], three["issues"]
    moved = _person(db_session, "acc-m", (g["A"], 100, None), (g["B"], 100, date(2026, 11, 15)))
    _log(db_session, "w10", it["B"], moved, date(2026, 11, 10), 4.0)
    _log(db_session, "w20", it["B"], moved, date(2026, 11, 20), 6.0)

    rows = _flow(db_session)

    assert rows["A"].out_hours == 4.0
    assert rows["B"].in_hours == 4.0
    assert rows["B"].out_hours == 0.0


def test_shared_person_flow_split_by_shares(db_session, three):
    """Общий A 60 / B 40: работа в своих группах — не переток, вне их «ушло» делится по долям."""
    g, it = three["groups"], three["issues"]
    shared = _person(db_session, "acc-s", (g["A"], 60, None), (g["B"], 40, None))
    _log(db_session, "w1", it["B"], shared, date(2026, 11, 10), 5.0)
    _log(db_session, "w2", it["C"], shared, date(2026, 11, 11), 10.0)

    rows = _flow(db_session)

    assert rows["A"].out_hours == 6.0
    assert rows["B"].out_hours == 4.0
    assert rows["B"].in_hours == 0.0
    assert rows["C"].in_hours == 10.0


def test_worklog_exactly_on_transfer_date_counts_new_group(db_session, three):
    """Списание ровно в день перевода — уже по новой группе."""
    g, it = three["groups"], three["issues"]
    moved = _person(db_session, "acc-m2", (g["A"], 100, None), (g["B"], 100, date(2026, 11, 15)))
    _log(db_session, "w30", it["C"], moved, date(2026, 11, 15), 4.0)

    rows = _flow(db_session)

    assert rows["B"].out_hours == 4.0
    assert rows["C"].in_hours == 4.0
    assert "A" not in rows  # к дню списания человек уже не в группе A


def test_work_after_leaving_team_is_not_flow(db_session, three):
    """После выхода из команды человек — помощь извне, его группа не источник перетока."""
    g, it = three["groups"], three["issues"]
    left = _person(db_session, "acc-l", (g["A"], 100, None), left_at=date(2026, 11, 1))
    _log(db_session, "w1", it["B"], left, date(2026, 11, 10), 5.0)

    assert _flow(db_session) == {}
