"""Лесенка разрешения группы: явно -> от родителя -> по исполнителю."""

import pytest

from app.models import Employee, EmployeeTeam, Issue, Project, Team, TeamSubgroup
from app.services.subgroup_resolver import SubgroupResolver, SubgroupSource

TEAM = "Команда 1С (Бухгалтерия)"


@pytest.fixture
def setup(db_session):
    db_session.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    team = Team(name=TEAM, has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    calc = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    integ = TeamSubgroup(team_id=team.id, name="Интеграции", sort_order=2)
    db_session.add_all([calc, integ])
    emp = Employee(jira_account_id="acc-1", display_name="Иванов")
    db_session.add(emp)
    db_session.flush()
    db_session.add(
        EmployeeTeam(
            employee_id=emp.id, team=TEAM, is_primary=True, subgroup_id=integ.id
        )
    )
    db_session.commit()
    return {"team": team, "calc": calc, "integ": integ, "emp": emp}


def _issue(db_session, key, **kw):
    issue = Issue(
        jira_issue_id=key,
        key=key,
        summary=key,
        issue_type="Task",
        status="Open",
        project_id="p1",
        team=TEAM,
        **kw,
    )
    db_session.add(issue)
    db_session.commit()
    return issue


def test_explicit_wins(db_session, setup):
    issue = _issue(
        db_session, "OS-1", assigned_subgroup_id=setup["calc"].id,
        assignee_account_id="acc-1",
    )

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id == setup["calc"].id
    assert res.source == SubgroupSource.ASSIGNED


def test_inherited_from_parent(db_session, setup):
    parent = _issue(db_session, "OS-10", assigned_subgroup_id=setup["calc"].id)
    child = _issue(db_session, "OS-11", parent_id=parent.id, assignee_account_id="acc-1")

    res = SubgroupResolver(db_session).resolve_for_issue(child)

    assert res.subgroup_id == setup["calc"].id
    assert res.source == SubgroupSource.INHERITED
    assert res.source_entity_key == "OS-10"


def test_guess_from_assignee(db_session, setup):
    issue = _issue(db_session, "OS-2", assignee_account_id="acc-1")

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id == setup["integ"].id
    assert res.source == SubgroupSource.GUESS


def test_nothing_to_guess(db_session, setup):
    issue = _issue(db_session, "OS-3")

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id is None
    assert res.source == SubgroupSource.NONE


def test_team_without_subgroups_resolves_to_nothing(db_session, setup):
    setup["team"].has_subgroups = False
    db_session.commit()
    issue = _issue(
        db_session, "OS-4", assigned_subgroup_id=setup["calc"].id,
        assignee_account_id="acc-1",
    )

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id is None
    assert res.source == SubgroupSource.NONE


def test_group_of_another_team_is_ignored(db_session, setup):
    """Группа чужой команды не может утечь в задачу через переезд."""
    other = Team(name="Команда Б", has_subgroups=True)
    db_session.add(other)
    db_session.flush()
    alien = TeamSubgroup(team_id=other.id, name="Расчёты", sort_order=1)
    db_session.add(alien)
    db_session.commit()
    issue = _issue(db_session, "OS-5", assigned_subgroup_id=alien.id)

    res = SubgroupResolver(db_session).resolve_for_issue(issue)

    assert res.subgroup_id is None
    assert res.source == SubgroupSource.NONE
