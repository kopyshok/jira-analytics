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


class TestEmployeeTeamService:
    def _make_emp(self, db, eid="emp-x"):
        emp = Employee(
            id=eid, jira_account_id=f"acc-{eid}",
            display_name=eid, is_active=True,
            synced_at=datetime.utcnow(),
        )
        db.add(emp)
        db.commit()
        return emp

    def test_add_team_first_becomes_primary(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "Team A")
        rows = db_session.query(EmployeeTeam).filter_by(employee_id=emp.id).all()
        assert len(rows) == 1
        assert rows[0].is_primary is True

    def test_add_second_team_not_primary(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "A")
        svc.add_team(emp.id, "B")
        primaries = db_session.query(EmployeeTeam).filter_by(
            employee_id=emp.id, is_primary=True
        ).all()
        assert len(primaries) == 1
        assert primaries[0].team == "A"

    def test_set_primary_reassigns(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "A")
        svc.add_team(emp.id, "B")
        svc.set_primary(emp.id, "B")
        primaries = db_session.query(EmployeeTeam).filter_by(
            employee_id=emp.id, is_primary=True
        ).all()
        assert len(primaries) == 1
        assert primaries[0].team == "B"

    def test_remove_team_reassigns_primary_if_needed(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "A")
        svc.add_team(emp.id, "B")
        svc.remove_team(emp.id, "A")
        primaries = db_session.query(EmployeeTeam).filter_by(
            employee_id=emp.id, is_primary=True
        ).all()
        assert len(primaries) == 1
        assert primaries[0].team == "B"

    def test_remove_last_team_ok(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "A")
        svc.remove_team(emp.id, "A")
        assert db_session.query(EmployeeTeam).filter_by(employee_id=emp.id).count() == 0

    def test_legacy_team_column_mirrors_primary(self, db_session):
        """Employee.team всегда = имя primary team (derived). Пишется сервисом
        для обратной совместимости с существующими запросами."""
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "A")
        db_session.refresh(emp)
        assert emp.team == "A"
        svc.add_team(emp.id, "B")
        svc.set_primary(emp.id, "B")
        db_session.refresh(emp)
        assert emp.team == "B"
        svc.remove_team(emp.id, "B")
        db_session.refresh(emp)
        assert emp.team == "A"  # B removed, A was only remaining → auto-primary

    def test_replace_teams_non_empty_with_primary(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "Old")
        rows = svc.replace_teams(emp.id, ["A", "B", "C"], primary="B")
        names = sorted(r.team for r in rows)
        assert names == ["A", "B", "C"]
        primaries = [r for r in rows if r.is_primary]
        assert len(primaries) == 1
        assert primaries[0].team == "B"
        db_session.refresh(emp)
        assert emp.team == "B"

    def test_replace_teams_primary_defaults_to_first(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        rows = svc.replace_teams(emp.id, ["X", "Y"])
        primary = next(r for r in rows if r.is_primary)
        assert primary.team == "X"
        db_session.refresh(emp)
        assert emp.team == "X"

    def test_replace_teams_primary_not_in_list_falls_back_to_first(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        rows = svc.replace_teams(emp.id, ["A", "B"], primary="Nope")
        primary = next(r for r in rows if r.is_primary)
        assert primary.team == "A"
        db_session.refresh(emp)
        assert emp.team == "A"

    def test_replace_teams_empty_clears_all(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "A")
        svc.add_team(emp.id, "B")
        rows = svc.replace_teams(emp.id, [])
        assert rows == []
        db_session.refresh(emp)
        assert emp.team is None

    def test_add_team_idempotent_same_team(self, db_session):
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        first = svc.add_team(emp.id, "A")
        second = svc.add_team(emp.id, "A")
        # Same row, no duplicate
        assert first.id == second.id
        assert db_session.query(EmployeeTeam).filter_by(employee_id=emp.id).count() == 1
        assert second.is_primary is True  # First team always primary

    def test_add_team_idempotent_promotes_to_primary(self, db_session):
        """Если добавить уже существующую команду с is_primary=True — она должна
        стать primary (идемпотентный промоут)."""
        from app.services.employee_team_service import EmployeeTeamService
        emp = self._make_emp(db_session)
        svc = EmployeeTeamService(db_session)
        svc.add_team(emp.id, "A")
        svc.add_team(emp.id, "B")  # A is primary
        # Re-add B with is_primary=True — should promote
        result = svc.add_team(emp.id, "B", is_primary=True)
        assert result.is_primary is True
        # Verify DB state
        a = db_session.query(EmployeeTeam).filter_by(employee_id=emp.id, team="A").one()
        assert a.is_primary is False
