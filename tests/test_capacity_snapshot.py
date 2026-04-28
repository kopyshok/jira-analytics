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
