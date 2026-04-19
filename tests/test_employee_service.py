"""Тесты EmployeeService.recalc_active_by_categories."""

from datetime import datetime

import pytest

from app.models import Category, Employee, Issue, Project, Worklog
from app.services.employee_service import EmployeeService, RecalcStats


@pytest.fixture
def seed_categories(db_session):
    cats = [
        Category(id="c1", code="active_1", label="Active1", is_system=False),
        Category(id="c2", code="archive", label="Archive", is_system=True),
        Category(id="c3", code="archive_target", label="Archive target", is_system=True),
        Category(id="c4", code="initiatives_rfa", label="Initiatives", is_system=True),
    ]
    db_session.add_all(cats)
    db_session.commit()
    return cats


@pytest.fixture
def make_fixture(db_session, seed_categories):
    def _mk(employee_code: str, issue_category: str | None) -> tuple[Employee, Issue]:
        proj = Project(id=f"p_{employee_code}", jira_project_id=f"10{employee_code}",
                       key=f"P{employee_code}", name="P")
        emp = Employee(
            id=f"e_{employee_code}", jira_account_id=f"a_{employee_code}",
            display_name=f"Name {employee_code}", is_active=False,
        )
        issue = Issue(
            id=f"i_{employee_code}", jira_issue_id=f"200{employee_code}",
            key=f"K-{employee_code}", summary="x",
            project_id=proj.id, issue_type="Task", status="В работе",
            assigned_category=issue_category,
            # recalc смотрит на эффективную (денормализованную) категорию,
            # которую в реальном бэкенде выставляет MappingService.
            category=issue_category,
        )
        db_session.add_all([proj, emp, issue])
        db_session.flush()
        wl = Worklog(
            id=f"w_{employee_code}", jira_worklog_id=f"30{employee_code}",
            issue_id=issue.id, employee_id=emp.id,
            started_at=datetime(2026, 2, 1, 10, 0),
            hours=1.0, time_spent_seconds=3600,
        )
        db_session.add(wl)
        db_session.commit()
        return emp, issue
    return _mk


def test_active_when_logged_on_active_stack(db_session, make_fixture):
    emp, _ = make_fixture("A", "active_1")
    service = EmployeeService(db_session)
    stats = service.recalc_active_by_categories()
    assert isinstance(stats, RecalcStats)
    db_session.refresh(emp)
    assert emp.is_active is True


def test_active_when_logged_on_archive_target(db_session, make_fixture):
    emp, _ = make_fixture("B", "archive_target")
    EmployeeService(db_session).recalc_active_by_categories()
    db_session.refresh(emp)
    assert emp.is_active is True


def test_inactive_when_only_archive(db_session, make_fixture):
    emp, _ = make_fixture("C", "archive")
    EmployeeService(db_session).recalc_active_by_categories()
    db_session.refresh(emp)
    assert emp.is_active is False


def test_inactive_when_only_initiatives_rfa(db_session, make_fixture):
    emp, _ = make_fixture("D", "initiatives_rfa")
    EmployeeService(db_session).recalc_active_by_categories()
    db_session.refresh(emp)
    assert emp.is_active is False


def test_inactive_when_no_worklogs(db_session, seed_categories):
    emp = Employee(
        id="e_noop", jira_account_id="a_noop", display_name="Noop", is_active=True,
    )
    db_session.add(emp)
    db_session.commit()
    EmployeeService(db_session).recalc_active_by_categories()
    db_session.refresh(emp)
    assert emp.is_active is False


def test_idempotent(db_session, make_fixture):
    emp, _ = make_fixture("E", "active_1")
    svc = EmployeeService(db_session)
    a = svc.recalc_active_by_categories()
    b = svc.recalc_active_by_categories()
    assert a.total_active == b.total_active == 1
    assert b.activated == 0 and b.deactivated == 0
