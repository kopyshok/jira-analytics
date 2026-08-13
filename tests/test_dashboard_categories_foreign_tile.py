"""Незаполненные ворклоги на чужих задачах — отдельная плитка виджета категорий."""

from datetime import datetime

import pytest

from app.models import Category, Employee, EmployeeTeam, Issue, Project, Worklog
from app.services.analytics_service import FOREIGN_UNFILLED_KEY, AnalyticsService


@pytest.fixture
def facts(db_session):
    """Сотрудник «Альфы»: 3 ч на своей задаче, 5 ч на задаче «Беты», обе без категории."""
    db_session.add_all([
        Category(code="unfilled_worklog", label="Незаполненные / сомнительные worklog"),
        Category(code="development", label="Разработка"),
    ])
    emp = Employee(
        jira_account_id="acc-f", display_name="Иванов И.", is_active=True, role="dev",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Альфа", is_primary=True))

    project = Project(jira_project_id="10000", key="PRJ", name="Проект")
    db_session.add(project)
    db_session.flush()

    def _issue(jira_id: str, key: str, team, category="unfilled_worklog") -> Issue:
        i = Issue(
            jira_issue_id=jira_id, key=key, project_id=project.id, summary=key,
            issue_type="Task", status="Done", category=category,
            include_in_analysis=True, team=team,
        )
        db_session.add(i)
        db_session.flush()
        return i

    own = _issue("1", "PRJ-1", "Альфа")
    alien = _issue("2", "PRJ-2", "Бета")
    no_team = _issue("3", "PRJ-3", None)
    normal = _issue("4", "PRJ-4", "Бета", category="development")

    def _wl(issue, jira_id: str, hours: float) -> Worklog:
        return Worklog(
            jira_worklog_id=jira_id, issue_id=issue.id, employee_id=emp.id,
            started_at=datetime(2026, 2, 10, 10, 0),
            hours=hours, time_spent_seconds=int(hours * 3600),
        )

    db_session.add_all([
        _wl(own, "w1", 3.0),
        _wl(alien, "w2", 5.0),
        _wl(no_team, "w3", 2.0),
        _wl(normal, "w4", 7.0),
    ])
    db_session.commit()
    return emp


def _by_key(resp) -> dict:
    return {i.key: i.hours for i in resp.items}


def test_foreign_unfilled_goes_to_own_tile(db_session, facts):
    """Чужая задача без категории — в отдельной плитке; своя остаётся в корзине."""
    resp = AnalyticsService(db_session).get_dashboard_categories(
        year=2026, quarter=1, teams=["Альфа"],
    )
    hours = _by_key(resp)
    assert hours[FOREIGN_UNFILLED_KEY] == 7.0  # 5 ч чужой команды + 2 ч без команды
    assert hours["unfilled_worklog"] == 3.0
    # Категорированные часы чужой задачи остаются в своей категории.
    assert hours["development"] == 7.0
    assert resp.total_hours == 17.0


def test_no_team_filter_keeps_single_bucket(db_session, facts):
    """Без фильтра команды делить не на что — плитки «чужих» нет."""
    resp = AnalyticsService(db_session).get_dashboard_categories(year=2026, quarter=1)
    hours = _by_key(resp)
    assert FOREIGN_UNFILLED_KEY not in hours
    assert hours["unfilled_worklog"] == 10.0
    assert resp.total_hours == 17.0
