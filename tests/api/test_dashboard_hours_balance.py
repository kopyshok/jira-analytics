"""API tests for GET /api/v1/analytics/dashboard/hours-balance (Task 6 + 7)."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.employee import Employee
from app.models.issue import Issue
from app.models.project import Project
from app.models.worklog import Worklog


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def test_client(test_db_session):
    def _get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Task 6: summary endpoint
# ---------------------------------------------------------------------------


def test_hours_balance_returns_200_on_empty(test_client):
    """No params, no employees — 200, valid shape, employees: []."""
    r = test_client.get("/api/v1/analytics/dashboard/hours-balance")
    assert r.status_code == 200
    body = r.json()
    assert "period" in body
    assert "team_summary" in body
    assert body["employees"] == []
    # period must have from, to, working_days
    assert "from" in body["period"]
    assert "to" in body["period"]
    assert "working_days" in body["period"]
    # team_summary shape
    ts = body["team_summary"]
    assert ts["employees_count"] == 0
    assert ts["net_balance"] == 0


def test_hours_balance_default_period_from_jan_1(test_client):
    """Default period: from = current year Jan 1, to = today."""
    r = test_client.get("/api/v1/analytics/dashboard/hours-balance")
    assert r.status_code == 200
    body = r.json()
    today = date.today()
    period = body["period"]
    assert period["from"] == f"{today.year}-01-01"
    assert period["to"] == today.isoformat()


# ---------------------------------------------------------------------------
# Task 7: drill-in endpoint
# ---------------------------------------------------------------------------


def test_drill_in_404_on_missing_employee(test_client):
    """Non-existent employee id → 404."""
    r = test_client.get("/api/v1/analytics/dashboard/hours-balance/no-such-id")
    assert r.status_code == 404


def test_drill_in_returns_kpi_monthly_days(test_client, test_db_session):
    """Seed Employee + Issue + Worklog; verify shape and February overtime."""
    # Seed
    test_db_session.add(Project(
        id="proj-hb1",
        jira_project_id="HB-1",
        key="HB",
        name="HB Project",
    ))
    test_db_session.add(Employee(
        id="emp-hb1",
        jira_account_id="jira-hb1",
        display_name="Тестов Иван",
        is_active=True,
    ))
    test_db_session.add(Issue(
        id="iss-hb1",
        jira_issue_id="HB-100",
        key="HB-1",
        summary="Test issue",
        issue_type="Task",
        status="Open",
        project_id="proj-hb1",
    ))
    # 10 hours on a Tuesday in February (2026-02-03) → overtime on that day
    test_db_session.add(Worklog(
        id="wl-hb1",
        jira_worklog_id="j-hb1",
        issue_id="iss-hb1",
        employee_id="emp-hb1",
        hours=10.0,
        time_spent_seconds=int(10 * 3600),
        started_at=datetime(2026, 2, 3, 10, 0),
    ))
    test_db_session.commit()

    r = test_client.get(
        "/api/v1/analytics/dashboard/hours-balance/emp-hb1",
        params={"from": "2026-02-01", "to": "2026-02-28"},
    )
    assert r.status_code == 200
    body = r.json()

    # Top-level keys
    assert "employee" in body
    assert "kpi" in body
    assert "monthly" in body
    assert "days" in body

    # employee shape
    emp = body["employee"]
    assert emp["id"] == "emp-hb1"
    assert emp["full_name"] == "Тестов Иван"

    # kpi shape
    kpi = body["kpi"]
    assert "balance_hours" in kpi
    assert "overtime_days" in kpi
    assert "skip_days" in kpi

    # monthly is a list
    assert isinstance(body["monthly"], list)

    # days is a list
    assert isinstance(body["days"], list)

    # February entry has overtime_days >= 1
    feb_entries = [m for m in body["monthly"] if m["month"] == 2]
    assert len(feb_entries) == 1
    assert feb_entries[0]["overtime_days"] >= 1
