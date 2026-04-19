"""Tests for EmployeeTeam model."""

from datetime import datetime
import pytest

from app.models import Employee, EmployeeTeam


def test_employee_team_fields(db_session):
    emp = Employee(
        id="emp-1",
        jira_account_id="acc-1",
        display_name="Test",
        is_active=True,
        synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.commit()

    et = EmployeeTeam(
        id="et-1",
        employee_id=emp.id,
        team="Team A",
        is_primary=True,
    )
    db_session.add(et)
    db_session.commit()

    loaded = db_session.query(EmployeeTeam).one()
    assert loaded.employee_id == "emp-1"
    assert loaded.team == "Team A"
    assert loaded.is_primary is True
    assert loaded.created_at is not None


def test_employee_relationship_teams(db_session):
    emp = Employee(
        id="emp-2", jira_account_id="acc-2", display_name="E",
        is_active=True, synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(id="et-a", employee_id="emp-2", team="A", is_primary=True))
    db_session.add(EmployeeTeam(id="et-b", employee_id="emp-2", team="B", is_primary=False))
    db_session.commit()

    emp = db_session.query(Employee).filter_by(id="emp-2").one()
    team_names = sorted(t.team for t in emp.teams)
    assert team_names == ["A", "B"]
    assert emp.primary_team_name() == "A"


def test_issue_out_of_scope_defaults_false(db_session):
    from app.models import Project, Issue

    proj = Project(
        id="p-1", jira_project_id="10000", key="PRJ",
        name="Test",
        synced_at=datetime.utcnow(),
    )
    db_session.add(proj)
    issue = Issue(
        id="i-1", jira_issue_id="20000", key="PRJ-1",
        project_id="p-1", summary="t", issue_type="Task",
        status="Open", status_category="new",
        synced_at=datetime.utcnow(),
    )
    db_session.add(issue)
    db_session.commit()

    loaded = db_session.query(Issue).one()
    assert loaded.out_of_scope is False
