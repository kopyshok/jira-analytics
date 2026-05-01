"""Hierarchical analytics report — service-level tests."""
from datetime import datetime
import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Category, Employee, EmployeeTeam, Issue, MandatoryWorkType,
    Project, Role, Worklog,
)
from app.models.role_capacity_rule import RoleCapacityRule


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _seed_minimal(db):
    wt_support = MandatoryWorkType(
        id=str(uuid.uuid4()), code="support_consult",
        label="Сопровождение и консультация",
        is_active=True, sort_order=1, subtracts_from_pool=True, is_system=True,
    )
    wt_other = MandatoryWorkType(
        id=str(uuid.uuid4()), code="other_foreign", label="Прочие / Чужие задачи",
        is_active=True, sort_order=99, subtracts_from_pool=False, is_system=True,
    )
    db.add_all([wt_support, wt_other])
    db.flush()
    db.add(Category(
        id=str(uuid.uuid4()), code="support_consultation",
        label="Сопровождение", sort_order=0, work_type_id=wt_support.id, color="#0bc"
    ))
    db.add(Role(
        id=str(uuid.uuid4()), code="developer", label="Программист",
        color="#0c8", sort_order=0, is_active=True,
    ))
    db.commit()


def _seed_emp(db, name, team, role="developer"):
    emp = Employee(
        id=str(uuid.uuid4()), jira_account_id=f"acc-{uuid.uuid4()}",
        display_name=name, is_active=True, role=role,
    )
    db.add(emp)
    db.flush()
    db.add(EmployeeTeam(
        id=str(uuid.uuid4()), employee_id=emp.id,
        team=team, is_primary=True,
    ))
    db.commit()
    return emp


def _seed_issue(db, project, key, team, category, summary="t"):
    i = Issue(
        id=str(uuid.uuid4()), jira_issue_id=f"ji-{uuid.uuid4()}",
        key=key, summary=summary, issue_type="Задача",
        status="In Progress", status_category="indeterminate",
        project_id=project.id, category=category, team=team,
        participating_teams=json.dumps([]),
    )
    db.add(i)
    db.commit()
    return i


def _seed_project(db):
    p = Project(id=str(uuid.uuid4()), jira_project_id="10000",
                key="TEST", name="Test", is_active=True)
    db.add(p)
    db.commit()
    return p


def _seed_worklog(db, issue, emp, hours, day=15):
    db.add(Worklog(
        id=str(uuid.uuid4()), jira_worklog_id=f"wl-{uuid.uuid4()}",
        issue_id=issue.id, employee_id=emp.id,
        started_at=datetime(2026, 4, day, 10, 0, 0),
        time_spent_seconds=int(hours * 3600), hours=hours,
    ))
    db.commit()


def test_report_service_returns_tree(db_session):
    from app.services.analytics_service import AnalyticsService
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест Тест", "Команда A")
    issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue, emp, 4.0)

    svc = AnalyticsService(db_session)
    data = svc.get_hierarchical_report(year=2026, quarter=2, teams=["Команда A"])
    assert len(data.teams) == 1
    assert data.teams[0].team == "Команда A"
    assert data.teams[0].totals.fact_hours == 4.0
    assert data.grand_totals.fact_hours == 4.0
    role = data.teams[0].roles[0]
    assert role.role_code == "developer"
    emp_node = role.employees[0]
    assert emp_node.name == "Тест Тест"
    wt = emp_node.work_types[0]
    assert wt.label == "Сопровождение и консультация"
    cat = wt.categories[0]
    assert cat.category_code == "support_consultation"
    issue_node = cat.issues[0]
    assert issue_node.key == "T-1"
    assert issue_node.totals.fact_hours == 4.0


def test_report_employee_filter(db_session):
    from app.services.analytics_service import AnalyticsService
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp1 = _seed_emp(db_session, "Один", "Команда A")
    emp2 = _seed_emp(db_session, "Два", "Команда A")
    issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue, emp1, 3.0)
    _seed_worklog(db_session, issue, emp2, 5.0)

    svc = AnalyticsService(db_session)
    data = svc.get_hierarchical_report(
        year=2026, quarter=2, teams=["Команда A"], employee_id=emp1.id,
    )
    all_emps = [e for t in data.teams for r in t.roles for e in r.employees]
    assert len(all_emps) == 1
    assert all_emps[0].employee_id == emp1.id


def test_report_task_query_filter(db_session):
    from app.services.analytics_service import AnalyticsService
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест", "Команда A")
    issue1 = _seed_issue(db_session, project, "PROD-1", "Команда A",
                         "support_consultation", summary="Bugfix login")
    issue2 = _seed_issue(db_session, project, "OS-2", "Команда A",
                         "support_consultation", summary="Refactor module")
    _seed_worklog(db_session, issue1, emp, 2.0)
    _seed_worklog(db_session, issue2, emp, 3.0)

    svc = AnalyticsService(db_session)
    data = svc.get_hierarchical_report(
        year=2026, quarter=2, teams=["Команда A"], task_query="bugfix",
    )
    all_issues = [
        i for t in data.teams for r in t.roles for e in r.employees
        for w in e.work_types for c in w.categories for i in c.issues
    ]
    assert len(all_issues) == 1
    assert all_issues[0].key == "PROD-1"


def test_report_plan_hours_at_employee_level(db_session):
    from app.services.analytics_service import AnalyticsService
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест", "Команда A")
    # support_consult, 50% от нормы
    wt_support = db_session.query(MandatoryWorkType).filter_by(code="support_consult").first()
    db_session.add(RoleCapacityRule(
        id=str(uuid.uuid4()), year=2026, quarter=2, role="developer",
        work_type_id=wt_support.id, percent_of_norm=50.0,
    ))
    db_session.commit()
    issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue, emp, 2.0)

    svc = AnalyticsService(db_session)
    data = svc.get_hierarchical_report(year=2026, quarter=2, teams=["Команда A"])
    emp_node = data.teams[0].roles[0].employees[0]
    assert emp_node.totals.plan_hours is not None
    assert emp_node.totals.plan_hours > 0
    sup_wt = next(w for w in emp_node.work_types if w.label == "Сопровождение и консультация")
    assert sup_wt.totals.plan_hours is not None
