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
        EmployeeTeam(employee_id=a.id, team=TEAM, is_primary=True, subgroup_id=calc.id),
        EmployeeTeam(employee_id=b.id, team=TEAM, is_primary=True, subgroup_id=integ.id),
        EmployeeTeam(employee_id=alien.id, team=OTHER_TEAM, is_primary=True),
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
