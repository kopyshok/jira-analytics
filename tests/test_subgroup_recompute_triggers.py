"""Действующая группа задачи обновляется сама, без ручного пересчёта."""

import pytest

from app.models import Employee, EmployeeTeam, Issue, Project, Team, TeamSubgroup
from app.services.team_registry_service import TeamRegistryService

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
    db_session.add(EmployeeTeam(employee_id=emp.id, team=TEAM, is_primary=True))
    issue = Issue(
        jira_issue_id="OS-1",
        key="OS-1",
        summary="OS-1",
        issue_type="Task",
        status="Open",
        project_id="p1",
        team=TEAM,
        assignee_account_id="acc-1",
    )
    db_session.add(issue)
    db_session.commit()
    return {"calc": calc, "integ": integ, "emp": emp, "issue": issue}


def test_employee_assignment_updates_guess(db_session, setup):
    svc = TeamRegistryService(db_session)

    svc.assign_employee(setup["emp"].id, TEAM, setup["integ"].id)
    db_session.expire_all()
    assert setup["issue"].effective_subgroup_id == setup["integ"].id

    svc.assign_employee(setup["emp"].id, TEAM, None)
    db_session.expire_all()
    assert setup["issue"].effective_subgroup_id is None


def test_disabling_flag_clears_column(db_session, setup):
    svc = TeamRegistryService(db_session)
    svc.assign_employee(setup["emp"].id, TEAM, setup["calc"].id)

    svc.set_has_subgroups(TEAM, False)
    db_session.expire_all()
    assert setup["issue"].effective_subgroup_id is None

    svc.set_has_subgroups(TEAM, True)
    db_session.expire_all()
    assert setup["issue"].effective_subgroup_id == setup["calc"].id


def test_deleting_subgroup_clears_column(db_session, setup):
    svc = TeamRegistryService(db_session)
    svc.assign_employee(setup["emp"].id, TEAM, setup["calc"].id)
    assert setup["issue"].effective_subgroup_id == setup["calc"].id

    svc.delete_subgroup(setup["calc"].id)
    db_session.expire_all()
    assert setup["issue"].effective_subgroup_id is None
