"""Cross-team routing in dashboard NormWork widget."""

from datetime import datetime
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import (
    Category,
    Employee,
    EmployeeTeam,
    Issue,
    MandatoryWorkType,
    Project,
    Role,
    Worklog,
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
    session = Session()
    try:
        yield session
    finally:
        session.close()
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


def _seed_work_types_and_categories(db):
    """Минимальный сидинг: other_foreign + support_consult + категория."""
    other = MandatoryWorkType(
        id=str(uuid.uuid4()),
        code="other_foreign",
        label="Прочие / Чужие задачи",
        is_active=True,
        sort_order=99,
        subtracts_from_pool=False,
        is_system=True,
    )
    support_wt = MandatoryWorkType(
        id=str(uuid.uuid4()),
        code="support_consult",
        label="Сопровождение и консультация",
        is_active=True,
        sort_order=1,
        subtracts_from_pool=True,
        is_system=True,
    )
    db.add_all([other, support_wt])
    db.flush()
    cat = Category(
        id=str(uuid.uuid4()),
        code="support_consultation",
        label="Сопровождение",
        sort_order=0,
        work_type_id=support_wt.id,
    )
    db.add(cat)
    role = Role(
        id=str(uuid.uuid4()),
        code="developer",
        label="Программист",
        color="#0c8",
        sort_order=0,
        is_active=True,
    )
    db.add(role)
    db.commit()
    return other, support_wt


def _seed_project(db):
    project = Project(
        id=str(uuid.uuid4()),
        jira_project_id="10000",
        key="TEST",
        name="Test Project",
        is_active=True,
    )
    db.add(project)
    db.commit()
    return project


def _seed_employee(db, name, team):
    emp = Employee(
        id=str(uuid.uuid4()),
        jira_account_id=f"acc-{uuid.uuid4()}",
        display_name=name,
        is_active=True,
        role="developer",
    )
    db.add(emp)
    db.flush()
    if team is not None:
        db.add(
            EmployeeTeam(
                id=str(uuid.uuid4()),
                employee_id=emp.id,
                team=team,
                is_primary=True,
            )
        )
    db.commit()
    return emp


def _seed_issue(db, project, key, team, parts=None, category="support_consultation"):
    issue = Issue(
        id=str(uuid.uuid4()),
        jira_issue_id=f"ji-{uuid.uuid4()}",
        key=key,
        summary=key,
        issue_type="Задача",
        status="In Progress",
        project_id=project.id,
        category=category,
        team=team,
        participating_teams=json.dumps(parts or []),
    )
    db.add(issue)
    db.commit()
    return issue


def _seed_worklog(db, issue, emp, hours):
    db.add(
        Worklog(
            id=str(uuid.uuid4()),
            jira_worklog_id=f"wl-{uuid.uuid4()}",
            issue_id=issue.id,
            employee_id=emp.id,
            started_at=datetime(2026, 4, 15, 10, 0, 0),
            time_spent_seconds=int(hours * 3600),
            hours=hours,
        )
    )
    db.commit()


def _find_emp_breakdown(data, emp_id):
    for role_grp in data["roles"]:
        for emp_block in role_grp["employees"]:
            if emp_block["employee_id"] == emp_id:
                return emp_block
    return None


def _wt_label_hours(emp_block, label_substr):
    if emp_block is None:
        return None
    for wt in emp_block["work_types"]:
        if label_substr in wt["label"]:
            return wt["fact_hours"]
    return None


def test_cross_team_worklog_routes_to_other_foreign(db_session, client):
    _seed_work_types_and_categories(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Тестов Тест", "Команда A")
    issue = _seed_issue(db_session, project, "FOR-1", team="Команда B")
    _seed_worklog(db_session, issue, emp, 5.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    assert resp.status_code == 200
    block = _find_emp_breakdown(resp.json(), emp.id)
    assert _wt_label_hours(block, "Прочие") == 5.0
    # должно НЕ попасть в Сопровождение
    assert _wt_label_hours(block, "Сопровождение") in (None, 0.0)


def test_own_team_worklog_routes_to_category_work_type(db_session, client):
    _seed_work_types_and_categories(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Свой Свой", "Команда A")
    issue = _seed_issue(db_session, project, "OWN-1", team="Команда A")
    _seed_worklog(db_session, issue, emp, 4.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    block = _find_emp_breakdown(resp.json(), emp.id)
    assert _wt_label_hours(block, "Сопровождение") == 4.0
    assert _wt_label_hours(block, "Прочие") in (None, 0.0)


def test_participating_team_means_own(db_session, client):
    _seed_work_types_and_categories(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Участник", "Команда A")
    issue = _seed_issue(
        db_session, project, "PART-1", team="Команда B", parts=["Команда A"]
    )
    _seed_worklog(db_session, issue, emp, 3.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    block = _find_emp_breakdown(resp.json(), emp.id)
    assert _wt_label_hours(block, "Сопровождение") == 3.0
    assert _wt_label_hours(block, "Прочие") in (None, 0.0)


def test_empty_issue_team_is_foreign(db_session, client):
    _seed_work_types_and_categories(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Пуст Тс", "Команда A")
    issue = _seed_issue(db_session, project, "EMPTY-1", team=None)
    _seed_worklog(db_session, issue, emp, 2.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    block = _find_emp_breakdown(resp.json(), emp.id)
    assert _wt_label_hours(block, "Прочие") == 2.0


def test_other_foreign_row_visible_when_plan_zero_fact_positive(db_session, client):
    """Строка other_foreign показывается с plan=0 fact>0 (пользовательский фронт перекрасит в красный)."""
    _seed_work_types_and_categories(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "План Ноль", "Команда A")
    issue = _seed_issue(db_session, project, "ZP-1", team="Команда B")
    _seed_worklog(db_session, issue, emp, 6.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    block = _find_emp_breakdown(resp.json(), emp.id)
    assert block is not None
    other_row = next(
        (wt for wt in block["work_types"] if "Прочие" in wt["label"]), None
    )
    assert other_row is not None, "Строка other_foreign должна быть в ответе"
    assert other_row["plan_hours"] == 0
    assert other_row["fact_hours"] == 6.0
    assert other_row["pct"] == 0.0  # план 0 → pct=0 по текущей логике, фронт сам красит
