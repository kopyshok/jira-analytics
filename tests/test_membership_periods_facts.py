"""Списание попадает в команду только за дни участия.

Проверяем через живой публичный метод виджета категорий: он режет факт
по команде сотрудника, поэтому выбытие должно отсекать более поздние
ворклоги.
"""

from datetime import date, datetime

import pytest

from app.models import Category, Employee, EmployeeTeam, Issue, Project, Worklog
from app.services.analytics_service import AnalyticsService


def _worklog(issue, emp, jira_id: str, started: datetime) -> Worklog:
    return Worklog(
        jira_worklog_id=jira_id,
        issue_id=issue.id,
        employee_id=emp.id,
        started_at=started,
        hours=8.0,
        time_spent_seconds=8 * 3600,
    )


@pytest.fixture
def facts(db_session):
    """Сотрудник «Альфы» с выбытием 15 февраля + два ворклога: январь и март."""
    db_session.add(Category(code="development", label="Разработка"))
    emp = Employee(
        jira_account_id="acc-1",
        display_name="Иванов И.",
        is_active=True,
        role="dev",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(
        EmployeeTeam(
            employee_id=emp.id,
            team="Альфа",
            is_primary=True,
            joined_at=date(2026, 1, 1),
            left_at=date(2026, 2, 15),
        )
    )
    project = Project(jira_project_id="10000", key="PRJ", name="Проект")
    db_session.add(project)
    db_session.flush()
    issue = Issue(
        jira_issue_id="20000",
        key="PRJ-1",
        project_id=project.id,
        summary="Задача",
        issue_type="Task",
        status="Done",
        category="development",
        include_in_analysis=True,
    )
    db_session.add(issue)
    db_session.flush()
    db_session.add_all([
        _worklog(issue, emp, "w1", datetime(2026, 1, 20, 10, 0)),
        _worklog(issue, emp, "w2", datetime(2026, 3, 10, 10, 0)),
    ])
    db_session.commit()
    return emp


def test_worklog_before_departure_counts(db_session, facts):
    """Списание до выбытия — в команде."""
    resp = AnalyticsService(db_session).get_dashboard_categories(
        year=2026, quarter=1, month=1, teams=["Альфа"],
    )
    assert resp.total_hours == 8.0


def test_worklog_after_departure_excluded(db_session, facts):
    """Списание после выбытия — не в команде."""
    resp = AnalyticsService(db_session).get_dashboard_categories(
        year=2026, quarter=1, month=3, teams=["Альфа"],
    )
    assert resp.total_hours == 0.0


def test_membership_without_dates_counts_always(db_session):
    """Участие без дат — поведение прежнее, весь факт в команде."""
    db_session.add(Category(code="development", label="Разработка"))
    emp = Employee(
        jira_account_id="acc-2",
        display_name="Петров П.",
        is_active=True,
        role="dev",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(
        EmployeeTeam(employee_id=emp.id, team="Бета", is_primary=True)
    )
    project = Project(jira_project_id="10001", key="PRJ2", name="Проект 2")
    db_session.add(project)
    db_session.flush()
    issue = Issue(
        jira_issue_id="20001",
        key="PRJ2-1",
        project_id=project.id,
        summary="Задача",
        issue_type="Task",
        status="Done",
        category="development",
        include_in_analysis=True,
    )
    db_session.add(issue)
    db_session.flush()
    db_session.add(_worklog(issue, emp, "w3", datetime(2026, 3, 10, 10, 0)))
    db_session.commit()

    resp = AnalyticsService(db_session).get_dashboard_categories(
        year=2026, quarter=1, month=3, teams=["Бета"],
    )
    assert resp.total_hours == 8.0
