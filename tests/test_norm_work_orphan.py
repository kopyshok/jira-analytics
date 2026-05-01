"""Orphan-bucket routing in dashboard NormWork widget."""

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


def _seed_base(db):
    """work_types + 1 категория с work_type + 1 категория без work_type + 1 роль."""
    other = MandatoryWorkType(
        id=str(uuid.uuid4()), code="other_foreign", label="Прочие / Чужие задачи",
        is_active=True, sort_order=99, subtracts_from_pool=False, is_system=True,
    )
    support_wt = MandatoryWorkType(
        id=str(uuid.uuid4()), code="support_consult", label="Сопровождение и консультация",
        is_active=True, sort_order=1, subtracts_from_pool=True, is_system=True,
    )
    db.add_all([other, support_wt])
    db.flush()
    db.add_all([
        Category(
            id=str(uuid.uuid4()), code="support_consultation", label="Сопровождение",
            sort_order=0, work_type_id=support_wt.id,
        ),
        # Категория без work_type — её ворклоги должны попасть в orphan
        Category(
            id=str(uuid.uuid4()), code="archive", label="Архив",
            sort_order=10, work_type_id=None,
        ),
    ])
    db.add(Role(
        id=str(uuid.uuid4()), code="developer", label="Программист",
        color="#0c8", sort_order=0, is_active=True,
    ))
    db.commit()
    return other, support_wt


def _seed_project(db):
    p = Project(id=str(uuid.uuid4()), jira_project_id="10000", key="TEST",
                name="Test Project", is_active=True)
    db.add(p)
    db.commit()
    return p


def _seed_employee(db, name, team):
    emp = Employee(
        id=str(uuid.uuid4()), jira_account_id=f"acc-{uuid.uuid4()}",
        display_name=name, is_active=True, role="developer",
    )
    db.add(emp)
    db.flush()
    if team is not None:
        db.add(EmployeeTeam(
            id=str(uuid.uuid4()), employee_id=emp.id, team=team, is_primary=True,
        ))
    db.commit()
    return emp


def _seed_issue(db, project, key, team, category):
    i = Issue(
        id=str(uuid.uuid4()), jira_issue_id=f"ji-{uuid.uuid4()}",
        key=key, summary=key, issue_type="Задача", status="In Progress",
        project_id=project.id, category=category, team=team,
        participating_teams=json.dumps([]),
    )
    db.add(i)
    db.commit()
    return i


def _seed_worklog(db, issue, emp, hours):
    db.add(Worklog(
        id=str(uuid.uuid4()), jira_worklog_id=f"wl-{uuid.uuid4()}",
        issue_id=issue.id, employee_id=emp.id,
        started_at=datetime(2026, 4, 15, 10, 0, 0),
        time_spent_seconds=int(hours * 3600), hours=hours,
    ))
    db.commit()


def _find_emp(data, emp_id):
    for grp in data["roles"]:
        for emp in grp["employees"]:
            if emp["employee_id"] == emp_id:
                return emp
    return None


def _wt_by_id(emp, wt_id):
    if emp is None:
        return None
    for wt in emp["work_types"]:
        if wt["work_type_id"] == wt_id:
            return wt
    return None


ORPHAN_ID = "__unmapped__"


def test_worklog_on_issue_without_category_routes_to_orphan(db_session, client):
    _seed_base(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Без Категории", "Команда A")
    issue = _seed_issue(db_session, project, "NC-1", team="Команда A", category=None)
    _seed_worklog(db_session, issue, emp, 4.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    assert resp.status_code == 200
    emp_block = _find_emp(resp.json(), emp.id)
    orphan = _wt_by_id(emp_block, ORPHAN_ID)
    assert orphan is not None
    assert orphan["fact_hours"] == 4.0
    assert orphan["plan_hours"] == 0
    assert "Не указана категория" in orphan["label"]


def test_worklog_on_category_without_work_type_routes_to_orphan(db_session, client):
    _seed_base(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Архив Архивыч", "Команда A")
    issue = _seed_issue(db_session, project, "ARC-1", team="Команда A", category="archive")
    _seed_worklog(db_session, issue, emp, 9.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    emp_block = _find_emp(resp.json(), emp.id)
    orphan = _wt_by_id(emp_block, ORPHAN_ID)
    assert orphan is not None
    assert orphan["fact_hours"] == 9.0


def test_foreign_team_beats_orphan_when_no_category(db_session, client):
    _seed_base(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Чужой Без Категории", "Команда A")
    issue = _seed_issue(db_session, project, "FNC-1", team="Команда B", category=None)
    _seed_worklog(db_session, issue, emp, 7.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    emp_block = _find_emp(resp.json(), emp.id)
    orphan = _wt_by_id(emp_block, ORPHAN_ID)
    foreign = next((w for w in emp_block["work_types"] if "Прочие" in w["label"]), None)
    assert orphan is None or orphan.get("fact_hours", 0) == 0
    assert foreign is not None and foreign["fact_hours"] == 7.0


def test_no_orphan_row_when_zero_orphan_hours(db_session, client):
    _seed_base(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Чистый", "Команда A")
    issue = _seed_issue(db_session, project, "OK-1", team="Команда A",
                        category="support_consultation")
    _seed_worklog(db_session, issue, emp, 5.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    emp_block = _find_emp(resp.json(), emp.id)
    orphan = _wt_by_id(emp_block, ORPHAN_ID)
    assert orphan is None, "orphan-строка не должна появляться при нулевом факте"


def test_total_fact_includes_orphan(db_session, client):
    _seed_base(db_session)
    project = _seed_project(db_session)
    emp = _seed_employee(db_session, "Микс", "Команда A")
    own = _seed_issue(db_session, project, "MIX-1", team="Команда A",
                      category="support_consultation")
    arc = _seed_issue(db_session, project, "MIX-2", team="Команда A", category="archive")
    _seed_worklog(db_session, own, emp, 10.0)
    _seed_worklog(db_session, arc, emp, 3.0)

    resp = client.get(
        "/api/v1/analytics/dashboard/norm-work",
        params={"year": 2026, "quarter": 2, "teams": "Команда A"},
    )
    emp_block = _find_emp(resp.json(), emp.id)
    assert emp_block["fact_hours"] == 13.0
    sup = next(w for w in emp_block["work_types"] if "Сопровождение" in w["label"])
    orph = _wt_by_id(emp_block, ORPHAN_ID)
    assert sup["fact_hours"] == 10.0
    assert orph["fact_hours"] == 3.0
