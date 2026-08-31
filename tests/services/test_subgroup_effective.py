"""Материализованная действующая группа задачи.

Пересчёт обязан давать ровно то же, что даёт лесенка построчно, иначе витрины
и стопка разбора начнут расходиться.
"""

import pytest

from app.models import Employee, EmployeeTeam, Issue, Project, Team, TeamSubgroup
from app.services.subgroup_resolver import SubgroupResolver

TEAM = "Команда 1С (Бухгалтерия)"
OTHER_TEAM = "Команда 2"


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


def _issue(db_session, key, team=TEAM, **kw):
    issue = Issue(
        jira_issue_id=key,
        key=key,
        summary=key,
        issue_type="Task",
        status="Open",
        project_id="p1",
        team=team,
        **kw,
    )
    db_session.add(issue)
    db_session.commit()
    return issue


def test_matches_row_by_row_resolution(db_session, setup):
    parent = _issue(db_session, "OS-1", assigned_subgroup_id=setup["calc"].id)
    child = _issue(db_session, "OS-2", parent_id=parent.id)
    guessed = _issue(db_session, "OS-3", assignee_account_id="acc-1")
    orphan = _issue(db_session, "OS-4")

    SubgroupResolver(db_session).recompute_effective()
    db_session.expire_all()

    assert parent.effective_subgroup_id == setup["calc"].id     # явно
    assert child.effective_subgroup_id == setup["calc"].id      # от родителя
    assert guessed.effective_subgroup_id == setup["integ"].id   # по исполнителю
    assert orphan.effective_subgroup_id is None


def test_other_team_untouched(db_session, setup):
    alien = _issue(
        db_session, "OS-9", team=OTHER_TEAM, assigned_subgroup_id=setup["calc"].id
    )

    SubgroupResolver(db_session).recompute_effective()
    db_session.expire_all()

    assert alien.effective_subgroup_id is None


def test_disabling_flag_clears_column(db_session, setup):
    issue = _issue(db_session, "OS-5", assigned_subgroup_id=setup["calc"].id)
    SubgroupResolver(db_session).recompute_effective()
    db_session.expire_all()
    assert issue.effective_subgroup_id == setup["calc"].id

    setup["team"].has_subgroups = False
    db_session.commit()
    SubgroupResolver(db_session).recompute_effective()
    db_session.expire_all()

    assert issue.effective_subgroup_id is None


def test_second_pass_writes_nothing(db_session, setup):
    _issue(db_session, "OS-6", assigned_subgroup_id=setup["calc"].id)
    _issue(db_session, "OS-7", assignee_account_id="acc-1")

    assert SubgroupResolver(db_session).recompute_effective() == 2
    assert SubgroupResolver(db_session).recompute_effective() == 0


def test_single_team_scope(db_session, setup):
    """Пересчёт по одной команде не трогает задачи остальных."""
    other = Team(name=OTHER_TEAM, has_subgroups=True)
    db_session.add(other)
    db_session.flush()
    grp = TeamSubgroup(team_id=other.id, name="Прочее", sort_order=1)
    db_session.add(grp)
    db_session.commit()

    mine = _issue(db_session, "OS-10", assigned_subgroup_id=setup["calc"].id)
    theirs = _issue(db_session, "OS-11", team=OTHER_TEAM, assigned_subgroup_id=grp.id)

    SubgroupResolver(db_session).recompute_effective(team=TEAM)
    db_session.expire_all()

    assert mine.effective_subgroup_id == setup["calc"].id
    assert theirs.effective_subgroup_id is None
