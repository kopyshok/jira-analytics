"""ProjectsService: list_projects + get_project_detail."""
import pytest
from datetime import datetime

from app.models.issue import Issue
from app.models.project import Project
from app.models.worklog import Worklog
from app.models.employee import Employee
from app.models.category import Category
from app.services.projects_service import ProjectsService


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_project(db, pid: str, key: str, name: str = "Project") -> Project:
    p = Project(id=pid, jira_project_id=pid, key=key, name=name)
    db.add(p)
    db.commit()
    return p


def _make_category(db, code: str, label: str, color: str = "#000") -> Category:
    cat = db.query(Category).filter_by(code=code).first()
    if cat:
        return cat
    import uuid
    cat = Category(id=str(uuid.uuid4()), code=code, label=label, color=color, sort_order=1, is_system=False)
    db.add(cat)
    db.commit()
    return cat


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_list_projects_filters_by_quarterly_categories(db_session):
    db = db_session
    _make_project(db, "p1", "PRJ1")
    db.add(Issue(id="i1", jira_issue_id="1", key="PRJ1-1", summary="Q",
                 issue_type="Epic", status="Done", project_id="p1",
                 category="quarterly_tasks", include_in_analysis=True))
    db.add(Issue(id="i2", jira_issue_id="2", key="PRJ1-2", summary="A",
                 issue_type="Epic", status="Done", project_id="p1",
                 category="archive_target", include_in_analysis=True))
    db.add(Issue(id="i3", jira_issue_id="3", key="PRJ1-3", summary="X",
                 issue_type="Epic", status="Done", project_id="p1",
                 category="tech_debt", include_in_analysis=True))
    db.commit()

    items = ProjectsService(db).list_projects()
    keys = {item.key for item in items}
    assert "PRJ1-1" in keys
    assert "PRJ1-2" in keys
    assert "PRJ1-3" not in keys


def test_list_projects_includes_metrics(db_session):
    db = db_session
    _make_project(db, "p2", "PRJ2")
    parent = Issue(id="ip", jira_issue_id="100", key="PRJ2-100", summary="Parent",
                   issue_type="Epic", status="Done", project_id="p2",
                   category="quarterly_tasks", include_in_analysis=True)
    child = Issue(id="ic", jira_issue_id="101", key="PRJ2-101", summary="Child",
                  issue_type="Task", status="Done", project_id="p2",
                  parent_id="ip", category="tech_debt", include_in_analysis=True)
    emp = Employee(id="e1", jira_account_id="acc1", display_name="John", email="j@e", is_active=True)
    db.add_all([parent, child, emp])
    db.commit()

    db.add(Worklog(id="w1", jira_worklog_id="w1", issue_id="ic", employee_id="e1",
                   hours=10.0, time_spent_seconds=36000,
                   started_at=datetime(2026, 2, 12),
                   updated_at=datetime(2026, 2, 12)))
    db.add(Worklog(id="w2", jira_worklog_id="w2", issue_id="ic", employee_id="e1",
                   hours=5.0, time_spent_seconds=18000,
                   started_at=datetime(2026, 3, 25),
                   updated_at=datetime(2026, 3, 25)))
    db.commit()

    items = ProjectsService(db).list_projects()
    item = next((i for i in items if i.key == "PRJ2-100"), None)
    assert item is not None
    assert item.total_hours == 15.0
    assert item.child_count == 1
    assert item.employee_count == 1
    assert item.period_start == datetime(2026, 2, 12)
    assert item.period_end == datetime(2026, 3, 25)


def test_get_project_detail_aggregates(db_session):
    db = db_session
    _make_category(db, "tech_debt", "Tech Debt", "#00c9c8")
    _make_project(db, "p3", "PRJ3")
    parent = Issue(id="ip3", jira_issue_id="200", key="PRJ3-200", summary="Big",
                   issue_type="Epic", status="Done", project_id="p3",
                   category="quarterly_tasks", include_in_analysis=True,
                   rating_quality=5, rating_speed=4, rating_result=5)
    child = Issue(id="ic3", jira_issue_id="201", key="PRJ3-201", summary="Sub1",
                  issue_type="Task", status="Done", project_id="p3",
                  parent_id="ip3", category="tech_debt", include_in_analysis=True)
    e1 = Employee(id="e_a", jira_account_id="a1", display_name="Alice", email="a@e", is_active=True, team="A")
    e2 = Employee(id="e_b", jira_account_id="a2", display_name="Bob", email="b@e", is_active=True, team="B")
    db.add_all([parent, child, e1, e2])
    db.commit()

    db.add(Worklog(id="wa", jira_worklog_id="wa", issue_id="ic3", employee_id="e_a",
                   hours=20, time_spent_seconds=72000,
                   started_at=datetime(2026, 2, 1), updated_at=datetime(2026, 2, 1)))
    db.add(Worklog(id="wb", jira_worklog_id="wb", issue_id="ic3", employee_id="e_b",
                   hours=5, time_spent_seconds=18000,
                   started_at=datetime(2026, 2, 15), updated_at=datetime(2026, 2, 15)))
    db.commit()

    detail = ProjectsService(db).get_project_detail("PRJ3-200")
    assert detail is not None
    assert detail.key == "PRJ3-200"
    assert detail.total_hours == 25.0
    assert detail.employee_count == 2
    assert len(detail.categories) == 1
    assert detail.categories[0].code == "tech_debt"
    assert len(detail.employees) == 2
    assert detail.employees[0].name == "Alice"  # отсортированы по часам desc
    assert detail.employees[0].hours == 20.0
    assert detail.rating_quality == 5
    assert detail.rating_speed == 4
    assert detail.rating_result == 5


def test_get_project_detail_returns_none_for_non_quarterly(db_session):
    db = db_session
    _make_project(db, "p4", "PRJ4")
    db.add(Issue(id="ix", jira_issue_id="300", key="PRJ4-300", summary="X",
                 issue_type="Epic", status="Done", project_id="p4",
                 category="tech_debt", include_in_analysis=True))
    db.commit()
    assert ProjectsService(db).get_project_detail("PRJ4-300") is None
    assert ProjectsService(db).get_project_detail("PRJ4-NOTEXIST") is None


def test_list_projects_filters_by_team(db_session):
    """Глобальный team filter: проект попадает если есть worklog от сотрудника
    из выбранных команд."""
    db = db_session
    _make_project(db, "p5", "PRJ5")
    parent = Issue(id="ip5", jira_issue_id="400", key="PRJ5-400", summary="P",
                   issue_type="Epic", status="Done", project_id="p5",
                   category="quarterly_tasks", include_in_analysis=True)
    child = Issue(id="ic5", jira_issue_id="401", key="PRJ5-401", summary="S",
                  issue_type="Task", status="Done", project_id="p5",
                  parent_id="ip5", category="tech_debt", include_in_analysis=True)
    e_a = Employee(id="e_x", jira_account_id="x1", display_name="X", email="x@e", is_active=True, team="TeamA")
    e_b = Employee(id="e_y", jira_account_id="y1", display_name="Y", email="y@e", is_active=True, team="TeamB")
    db.add_all([parent, child, e_a, e_b])
    db.commit()
    db.add(Worklog(id="wA", jira_worklog_id="wA", issue_id="ic5", employee_id="e_x",
                   hours=10, time_spent_seconds=36000,
                   started_at=datetime(2026, 2, 1), updated_at=datetime(2026, 2, 1)))
    db.commit()

    # Фильтруем по TeamB — нет ни одного worklog от TeamB → проект отсутствует
    items = ProjectsService(db).list_projects(team_filter=["TeamB"])
    assert all(i.key != "PRJ5-400" for i in items)

    # Фильтр по TeamA — проект есть
    items_a = ProjectsService(db).list_projects(team_filter=["TeamA"])
    assert any(i.key == "PRJ5-400" for i in items_a)
