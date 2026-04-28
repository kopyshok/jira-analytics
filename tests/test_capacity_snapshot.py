"""Tests for norm and absence snapshots created during scenario approval."""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    Absence,
    AbsenceReason,
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    PlanningScenario,
    ScenarioRule,
)
from app.models.scenario_absence_snapshot import ScenarioAbsenceSnapshot
from app.models.scenario_norm_snapshot import ScenarioNormSnapshot


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
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


def test_approve_creates_norm_snapshots(client, db_session):
    """Approving scenario with rules creates ScenarioNormSnapshot rows."""
    wt = MandatoryWorkType(
        id="wt-t1", code="projects_t1", label="Проекты",
        is_active=True, sort_order=1, subtracts_from_pool=False,
    )
    db_session.add(wt)
    emp = Employee(
        id="emp-t1", jira_account_id="acc-t1", display_name="Тест",
        email="test1@test.com", is_active=True, role="analyst",
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id=_uid(), employee_id="emp-t1", team="TeamT1", is_primary=True,
    ))
    scenario = PlanningScenario(
        id="sc-t1", name="Q2 Test", quarter="Q2", year=2026,
        status="draft", team="TeamT1",
    )
    db_session.add(scenario)
    rule = ScenarioRule(
        id="sr-t1", scenario_id="sc-t1", role="analyst",
        work_type_id="wt-t1", percent_of_norm=30.0,
    )
    db_session.add(rule)
    db_session.commit()

    resp = client.post("/api/v1/planning/scenarios/sc-t1/approve")
    assert resp.status_code == 200

    norms = db_session.query(ScenarioNormSnapshot).filter(
        ScenarioNormSnapshot.employee_id == "emp-t1"
    ).all()
    assert len(norms) == 3  # 3 months in Q2
    assert all(n.work_type_label == "Проекты" for n in norms)
    assert all(n.role == "analyst" for n in norms)


def test_approve_creates_absence_snapshots(client, db_session):
    """Approving scenario snapshots absences for team employees."""
    emp = Employee(
        id="emp-t2", jira_account_id="acc-t2", display_name="Тест2",
        email="test2@test.com", is_active=True,
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id=_uid(), employee_id="emp-t2", team="TeamT2", is_primary=True,
    ))
    reason = AbsenceReason(
        id="ar-t1", code="vacation_t", label="Отпуск",
        is_planned=True, is_active=True, sort_order=0,
    )
    db_session.add(reason)
    absence = Absence(
        id="abs-t1", employee_id="emp-t2", reason_id="ar-t1",
        start_date=date(2026, 4, 14), end_date=date(2026, 4, 18), hours_total=40.0,
    )
    db_session.add(absence)
    scenario = PlanningScenario(
        id="sc-t2", name="Q2 B", quarter="Q2", year=2026,
        status="draft", team="TeamT2",
    )
    db_session.add(scenario)
    db_session.commit()

    resp = client.post("/api/v1/planning/scenarios/sc-t2/approve")
    assert resp.status_code == 200

    snaps = db_session.query(ScenarioAbsenceSnapshot).filter(
        ScenarioAbsenceSnapshot.original_absence_id == "abs-t1"
    ).all()
    assert len(snaps) == 1
    assert snaps[0].employee_id == "emp-t2"
    assert snaps[0].hours_total == 40.0
    assert snaps[0].reason_label == "Отпуск"


def test_capacity_diff_no_changes(client, db_session):
    """Diff returns has_changes=False when nothing changed after approval."""
    emp = Employee(id="emp-d1", jira_account_id="acc-d1", display_name="DiffTest", is_active=True)
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id=_uid(), employee_id="emp-d1", team="TeamD1", is_primary=True,
    ))
    scenario = PlanningScenario(id="sc-d1", name="Q2 Diff", quarter="Q2", year=2026, status="draft", team="TeamD1")
    db_session.add(scenario)
    db_session.commit()

    approve_resp = client.post("/api/v1/planning/scenarios/sc-d1/approve")
    assert approve_resp.status_code == 200

    resp = client.get("/api/v1/planning/scenarios/sc-d1/capacity-diff")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_changes"] is False


def test_capacity_diff_detects_removed_absence(client, db_session):
    """Diff detects absence removed after approval."""
    emp = Employee(id="emp-d2", jira_account_id="acc-d2", display_name="DiffTest2", is_active=True)
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id=_uid(), employee_id="emp-d2", team="TeamD2", is_primary=True,
    ))
    reason = AbsenceReason(
        id="ar-d1", code="vacation_d", label="Отпуск",
        is_planned=True, is_active=True, sort_order=0,
    )
    db_session.add(reason)
    absence = Absence(
        id="abs-d1", employee_id="emp-d2", reason_id="ar-d1",
        start_date=date(2026, 4, 7), end_date=date(2026, 4, 11), hours_total=40.0,
    )
    db_session.add(absence)
    scenario = PlanningScenario(id="sc-d2", name="Q2 Diff2", quarter="Q2", year=2026, status="draft", team="TeamD2")
    db_session.add(scenario)
    db_session.commit()

    approve_resp = client.post("/api/v1/planning/scenarios/sc-d2/approve")
    assert approve_resp.status_code == 200

    # Delete the absence after approval
    db_session.delete(absence)
    db_session.commit()

    resp = client.get("/api/v1/planning/scenarios/sc-d2/capacity-diff")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_changes"] is True
    emp_diff = data["changed_employees"][0]
    assert emp_diff["employee_id"] == "emp-d2"
    changes = emp_diff["months"][0]["absence_changes"]
    assert len(changes) == 1
    assert changes[0]["type"] == "removed"


def test_capacity_diff_detects_added_absence(client, db_session):
    """Diff detects absence added after approval."""
    emp = Employee(id="emp-d3", jira_account_id="acc-d3", display_name="DiffTest3", is_active=True)
    db_session.add(emp)
    db_session.add(EmployeeTeam(
        id=_uid(), employee_id="emp-d3", team="TeamD3", is_primary=True,
    ))
    scenario = PlanningScenario(id="sc-d3", name="Q2 Diff3", quarter="Q2", year=2026, status="draft", team="TeamD3")
    db_session.add(scenario)
    db_session.commit()

    # Approve with no absences
    approve_resp = client.post("/api/v1/planning/scenarios/sc-d3/approve")
    assert approve_resp.status_code == 200

    # Add absence AFTER approval
    reason3 = AbsenceReason(
        id="ar-d3", code="vacation_d3", label="Отпуск",
        is_planned=True, is_active=True, sort_order=0,
    )
    db_session.add(reason3)
    new_abs = Absence(
        id="abs-d2", employee_id="emp-d3", reason_id="ar-d3",
        start_date=date(2026, 5, 5), end_date=date(2026, 5, 9), hours_total=40.0,
    )
    db_session.add(new_abs)
    db_session.commit()

    resp = client.get("/api/v1/planning/scenarios/sc-d3/capacity-diff")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_changes"] is True
    changes = data["changed_employees"][0]["months"][0]["absence_changes"]
    assert any(c["type"] == "added" for c in changes)
