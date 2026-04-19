"""Endpoint smoke tests for /analytics/* with team filter."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    CategoryMapping,
    Employee,
    EmployeeTeam,
    Issue,
    Project,
    Worklog,
)
from app.services.categories import CategoryCode


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def setup_data(db_session):
    """Minimal seed: 2 employees, 2 projects, 3 issues, worklogs + category mappings.

    Mirrors tests/test_analytics_service.py::setup_data but duplicated locally
    to avoid risking regressions in the service tests.
    """
    alice = Employee(jira_account_id="a1", display_name="Alice")
    bob = Employee(jira_account_id="b1", display_name="Bob")
    db_session.add_all([alice, bob])
    db_session.flush()

    db_session.add_all([
        EmployeeTeam(employee_id=alice.id, team="Core", is_primary=True),
        EmployeeTeam(employee_id=bob.id, team="Mobile", is_primary=True),
    ])

    proj_a = Project(jira_project_id="pa", key="AAA", name="Alpha")
    proj_b = Project(jira_project_id="pb", key="BBB", name="Beta")
    db_session.add_all([proj_a, proj_b])
    db_session.flush()

    issue_a1 = Issue(
        jira_issue_id="ja1", key="AAA-1", summary="A1", issue_type="Task",
        status="Open", project_id=proj_a.id,
        team="Core", participating_teams='["Core","Mobile"]',
    )
    issue_a2 = Issue(
        jira_issue_id="ja2", key="AAA-2", summary="A2", issue_type="Task",
        status="Open", project_id=proj_a.id,
        team="Mobile", participating_teams='["Mobile"]',
    )
    issue_b1 = Issue(
        jira_issue_id="jb1", key="BBB-1", summary="B1", issue_type="Task",
        status="Open", project_id=proj_b.id,
        team=None, participating_teams='[]',
    )
    db_session.add_all([issue_a1, issue_a2, issue_b1])
    db_session.flush()

    worklogs = [
        Worklog(
            jira_worklog_id="wl1", started_at=datetime(2026, 1, 5, 10, 0, 0),
            hours=2.0, time_spent_seconds=7200, comment_text="work a1",
            issue_id=issue_a1.id, employee_id=alice.id,
        ),
        Worklog(
            jira_worklog_id="wl2", started_at=datetime(2026, 1, 6, 10, 0, 0),
            hours=3.0, time_spent_seconds=10800, comment_text="work a2",
            issue_id=issue_a2.id, employee_id=alice.id,
        ),
        Worklog(
            jira_worklog_id="wl3", started_at=datetime(2026, 1, 7, 10, 0, 0),
            hours=1.0, time_spent_seconds=3600, comment_text="work b1",
            issue_id=issue_b1.id, employee_id=alice.id,
        ),
        Worklog(
            jira_worklog_id="wl4", started_at=datetime(2026, 1, 5, 9, 0, 0),
            hours=4.0, time_spent_seconds=14400, comment_text="work b1 bob",
            issue_id=issue_b1.id, employee_id=bob.id,
        ),
        Worklog(
            jira_worklog_id="wl5", started_at=datetime(2026, 1, 8, 9, 0, 0),
            hours=2.0, time_spent_seconds=7200, comment_text="work a1 bob",
            issue_id=issue_a1.id, employee_id=bob.id,
        ),
    ]
    db_session.add_all(worklogs)
    db_session.flush()

    db_session.add_all([
        CategoryMapping(entity_type="worklog", entity_id=worklogs[0].id, category=CategoryCode.TECH_DEBT),
        CategoryMapping(entity_type="worklog", entity_id=worklogs[1].id, category=CategoryCode.TECH_DEBT),
        CategoryMapping(entity_type="worklog", entity_id=worklogs[2].id, category=CategoryCode.MEETINGS),
        CategoryMapping(entity_type="worklog", entity_id=worklogs[3].id, category=CategoryCode.MEETINGS),
        CategoryMapping(entity_type="worklog", entity_id=worklogs[4].id, category=CategoryCode.SUPPORT_CONSULTATION),
    ])
    db_session.commit()
    # Pin :memory: connection to test thread (see capacity endpoint tests)
    db_session.query(Employee).first()

    return {"alice": alice, "bob": bob}


def test_hours_by_employee_team_filter_smoke(client, db_session, setup_data):
    # Filter by Core via employees only — Alice in, Bob out
    resp = client.get(
        "/api/v1/analytics/hours/by-employee",
        params={"teams": "Core", "match_employees": "true", "match_issues": "false"},
    )
    assert resp.status_code == 200
    body = resp.json()
    labels = {row["label"] for row in body}
    assert "Alice" in labels
    assert "Bob" not in labels


def test_hours_by_employee_empty_teams_is_noop(client, db_session, setup_data):
    resp = client.get("/api/v1/analytics/hours/by-employee", params={"teams": ""})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2  # both Alice and Bob
