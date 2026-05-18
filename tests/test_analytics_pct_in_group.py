"""Тесты для новых полей NodeTotals: pct_in_group + foreign_*."""
import json
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    Category, Employee, EmployeeTeam, Issue, MandatoryWorkType,
    Project, Role, Worklog,
)


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


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


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
    p = Project(id=str(uuid.uuid4()), jira_project_id="10001",
                key="PCT", name="PctTest", is_active=True)
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pct_in_group_root_is_none(db_session, client):
    """На корневых строках (Team) pct_in_group = None — нет родителя в группе."""
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Тест", "Команда A")
    issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue, emp, 4.0)

    response = client.get(
        "/api/v1/analytics/report",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    assert response.status_code == 200
    data = response.json()
    for team in data["teams"]:
        assert team["totals"]["pct_in_group"] is None


def test_pct_in_group_child_sums_to_100(db_session, client):
    """Сумма pct_in_group у детей одного родителя должна быть ~100% (если факт > 0)."""
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp1 = _seed_emp(db_session, "Один", "Команда A")
    emp2 = _seed_emp(db_session, "Два", "Команда A")
    issue1 = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    issue2 = _seed_issue(db_session, project, "T-2", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue1, emp1, 3.0)
    _seed_worklog(db_session, issue2, emp2, 7.0)

    response = client.get(
        "/api/v1/analytics/report",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    data = response.json()
    for team in data["teams"]:
        if team["totals"]["fact_hours"] == 0:
            continue
        # Roles under team
        total = sum(
            r["totals"]["pct_in_group"] or 0 for r in team["roles"]
        )
        assert 99.0 <= total <= 101.0, f"team {team['team']}: roles pct_in_group sum = {total}"


def test_foreign_aggregation_at_grand_totals(db_session, client):
    """foreign_issue_count / foreign_hours propagate to grand_totals."""
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    # emp is in "Команда A" but logs work on a "Команда B" issue → foreign
    emp = _seed_emp(db_session, "Боец", "Команда A")
    own_issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    foreign_issue = _seed_issue(db_session, project, "T-2", "Команда B", "support_consultation")
    _seed_worklog(db_session, own_issue, emp, 6.0)
    _seed_worklog(db_session, foreign_issue, emp, 2.0)

    response = client.get(
        "/api/v1/analytics/report",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    assert response.status_code == 200
    data = response.json()
    grand = data["grand_totals"]
    assert grand["foreign_issue_count"] >= 1
    assert grand["foreign_hours"] > 0


def test_foreign_pct_correct_at_employee_level(db_session, client):
    """foreign_pct сотрудника = его чужие часы / все часы * 100."""
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp = _seed_emp(db_session, "Проверяемый", "Команда A")
    own_issue = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    foreign_issue = _seed_issue(db_session, project, "T-2", "Команда B", "support_consultation")
    _seed_worklog(db_session, own_issue, emp, 8.0)
    _seed_worklog(db_session, foreign_issue, emp, 2.0)

    response = client.get(
        "/api/v1/analytics/report",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    data = response.json()
    for team in data["teams"]:
        for role in team["roles"]:
            for emp_node in role["employees"]:
                t = emp_node["totals"]
                if t["fact_hours"] == 0:
                    continue
                expected = round(t["foreign_hours"] / t["fact_hours"] * 100, 1)
                assert abs(t["foreign_pct"] - expected) < 0.2, (
                    f"emp {emp_node['name']}: got {t['foreign_pct']}, expected {expected}"
                )


def test_pct_in_group_employee_under_role(db_session, client):
    """pct_in_group для сотрудника = его факт / факт роли * 100."""
    from app.services.analytics_service import AnalyticsService
    _seed_minimal(db_session)
    project = _seed_project(db_session)
    emp1 = _seed_emp(db_session, "А", "Команда A")
    emp2 = _seed_emp(db_session, "Б", "Команда A")
    issue1 = _seed_issue(db_session, project, "T-1", "Команда A", "support_consultation")
    issue2 = _seed_issue(db_session, project, "T-2", "Команда A", "support_consultation")
    _seed_worklog(db_session, issue1, emp1, 4.0)
    _seed_worklog(db_session, issue2, emp2, 6.0)

    svc = AnalyticsService(db_session)
    data = svc.get_hierarchical_report(year=2026, quarter=2, teams=["Команда A"])
    role = data.teams[0].roles[0]
    role_fact = role.totals.fact_hours
    for emp_node in role.employees:
        if emp_node.totals.fact_hours == 0:
            continue
        expected_pct = round(emp_node.totals.fact_hours / role_fact * 100, 1)
        assert abs((emp_node.totals.pct_in_group or 0) - expected_pct) < 0.2, (
            f"emp {emp_node.name}: pct_in_group={emp_node.totals.pct_in_group}, expected={expected_pct}"
        )
