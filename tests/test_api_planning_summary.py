"""Tests for /scenarios/{id}/resource-summary and copy-rules-from-template."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    Employee,
    EmployeeTeam,
    MandatoryWorkType,
    PlanningScenario,
    ScenarioRule,
)

TEAM = "test-team-summary"


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


def _emp(db, role: str, name: str) -> Employee:
    e = Employee(
        id=str(uuid.uuid4()),
        jira_account_id=str(uuid.uuid4()),
        display_name=name,
        email=f"{name.lower().replace(' ', '_')}@test.com",
        role=role,
        is_active=True,
    )
    db.add(e)
    db.add(EmployeeTeam(employee_id=e.id, team=TEAM, is_primary=True))
    return e


def _wt(db, label: str, code: str) -> MandatoryWorkType:
    wt = MandatoryWorkType(
        id=str(uuid.uuid4()),
        code=code,
        label=label,
        is_active=True,
        sort_order=1,
        subtracts_from_pool=True,
    )
    db.add(wt)
    return wt


def test_resource_summary_basic(client, db_session):
    _emp(db_session, "analyst", "Аналитик А")
    wt = _wt(db_session, "Орг. работы", "org")
    sc = PlanningScenario(
        id=str(uuid.uuid4()),
        name="Test",
        year=2026,
        quarter="Q2",
        status="draft",
        team=TEAM,
    )
    db_session.add(sc)
    db_session.flush()
    db_session.add(ScenarioRule(
        id=str(uuid.uuid4()),
        scenario_id=sc.id,
        role="analyst",
        work_type_id=wt.id,
        percent_of_norm=15.0,
    ))
    db_session.commit()

    resp = client.get(f"/api/v1/scenarios/{sc.id}/resource-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "analyst" in data["roles"]
    assert data["gross_by_role"]["analyst"] > 0
    wt_row = data["work_type_rows"][0]
    assert wt_row["work_type_label"] == "Орг. работы"
    assert wt_row["pct_by_role"]["analyst"] == 15.0
    gross = data["gross_by_role"]["analyst"]
    expected_avail = round(max(0, gross - gross * 0.15), 2)
    assert abs(data["available_by_role"]["analyst"] - expected_avail) < 1.0
