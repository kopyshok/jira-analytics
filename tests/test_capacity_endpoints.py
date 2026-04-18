"""Integration tests for capacity API endpoints."""

from datetime import datetime

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Employee, Issue, Project, Worklog


def test_team_endpoint_returns_fact_hours(db_session):
    emp = Employee(
        id="e1",
        jira_account_id="a1",
        display_name="Иванов",
        is_active=True,
    )
    proj = Project(id="p1", jira_project_id="100", key="P", name="P")
    issue = Issue(
        id="i1",
        jira_issue_id="1001",
        key="P-1",
        summary="x",
        project_id=proj.id,
        issue_type="Task",
        status="В работе",
    )
    db_session.add_all([emp, proj, issue])
    db_session.flush()
    db_session.add(
        Worklog(
            id="w1",
            jira_worklog_id="1",
            issue_id=issue.id,
            employee_id=emp.id,
            started_at=datetime(2026, 1, 15, 10, 0),
            hours=4.0,
            time_spent_seconds=14400,
        )
    )
    db_session.commit()
    db_session.query(Employee).first()  # pin :memory: connection

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        resp = client.get(
            "/api/v1/capacity/team",
            params={"year": 2026, "quarter": 1},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    rows = resp.json()
    row = next(r for r in rows if r["employee_id"] == "e1")
    assert "total_fact_hours" in row
    assert row["total_fact_hours"] == 4.0
    jan = next(m for m in row["months"] if m["month"] == 1)
    assert "fact_hours" in jan
    assert jan["fact_hours"] == 4.0
