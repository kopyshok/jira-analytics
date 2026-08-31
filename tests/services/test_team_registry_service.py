"""Реестр команд, группы внутри команды и приписка сотрудников."""

from app.models import Employee, EmployeeTeam, Issue, Project, Team, TeamSubgroup
from app.services.team_registry_service import TeamRegistryService


def test_team_defaults_to_no_subgroups(db_session):
    team = Team(name="Команда 1С (Бухгалтерия)")
    db_session.add(team)
    db_session.commit()

    assert team.has_subgroups is False
    assert team.subgroups == []


def test_subgroups_are_ordered_and_cascade(db_session):
    team = Team(name="Команда 1С (Бухгалтерия)", has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    db_session.add_all(
        [
            TeamSubgroup(team_id=team.id, name="Интеграции", sort_order=2),
            TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1),
        ]
    )
    db_session.commit()
    db_session.refresh(team)

    assert [s.name for s in team.subgroups] == ["Расчёты", "Интеграции"]

    db_session.delete(team)
    db_session.commit()
    assert db_session.query(TeamSubgroup).count() == 0


def test_membership_carries_subgroup(db_session):
    team = Team(name="Команда 1С (Бухгалтерия)", has_subgroups=True)
    db_session.add(team)
    db_session.flush()
    group = TeamSubgroup(team_id=team.id, name="Расчёты", sort_order=1)
    db_session.add(group)
    emp = Employee(jira_account_id="acc-1", display_name="Иванов")
    db_session.add(emp)
    db_session.flush()
    db_session.add(
        EmployeeTeam(
            employee_id=emp.id, team=team.name, is_primary=True, subgroup_id=group.id
        )
    )
    db_session.commit()

    row = db_session.query(EmployeeTeam).one()
    assert row.subgroup_id == group.id


def test_issue_subgroup_defaults(db_session):
    issue = Issue(
        jira_issue_id="10001",
        key="OS-1",
        summary="x",
        issue_type="Task",
        status="Open",
        project_id="p1",
    )

    assert issue.assigned_subgroup_id is None
    assert issue.subgroup_verified is None or issue.subgroup_verified is True


def test_sync_names_picks_up_teams_from_data(db_session):
    db_session.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    db_session.add(
        Issue(
            jira_issue_id="10001",
            key="OS-1",
            summary="x",
            issue_type="Task",
            status="Open",
            project_id="p1",
            team="Команда А",
        )
    )
    emp = Employee(jira_account_id="acc-1", display_name="Иванов")
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Команда Б", is_primary=True))
    db_session.commit()

    created = TeamRegistryService(db_session).sync_names()

    assert created == 2
    assert {t.name for t in db_session.query(Team).all()} == {"Команда А", "Команда Б"}

    assert TeamRegistryService(db_session).sync_names() == 0


def test_disable_keeps_subgroups(db_session):
    """Выключение признака ничего не удаляет — это путь отката."""
    service = TeamRegistryService(db_session)
    service.set_has_subgroups("Команда А", True)
    service.add_subgroup("Команда А", "Расчёты")

    team = service.set_has_subgroups("Команда А", False)

    assert team.has_subgroups is False
    assert [g.name for g in team.subgroups] == ["Расчёты"]


def test_assign_employee_covers_all_membership_periods(db_session):
    service = TeamRegistryService(db_session)
    team = service.set_has_subgroups("Команда А", True)
    group = service.add_subgroup(team.name, "Расчёты")
    emp = Employee(jira_account_id="acc-1", display_name="Иванов")
    db_session.add(emp)
    db_session.flush()
    db_session.add_all(
        [
            EmployeeTeam(employee_id=emp.id, team="Команда А", is_primary=True),
            EmployeeTeam(employee_id=emp.id, team="Команда А", is_primary=False),
        ]
    )
    db_session.commit()

    service.assign_employee(emp.id, "Команда А", group.id)

    rows = db_session.query(EmployeeTeam).filter(EmployeeTeam.employee_id == emp.id).all()
    assert {r.subgroup_id for r in rows} == {group.id}
