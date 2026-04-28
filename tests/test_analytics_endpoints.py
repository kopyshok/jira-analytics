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
def tc_client(testclient_db_session):
    """TestClient backed by StaticPool — safe for async ASGI dispatch threads."""
    def _get_db():
        yield testclient_db_session
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
    # Filter by Core (OR: employee team OR issue team) — Alice in (Core member),
    # Bob in too because wl5 is on AAA-1 which has team=Core.
    resp = client.get(
        "/api/v1/analytics/hours/by-employee",
        params={"teams": "Core"},
    )
    assert resp.status_code == 200
    body = resp.json()
    labels = {row["label"] for row in body}
    assert "Alice" in labels
    assert "Bob" in labels  # wl5 on AAA-1 (team=Core) pulls Bob in via issue branch


def test_hours_by_employee_empty_teams_is_noop(client, db_session, setup_data):
    resp = client.get("/api/v1/analytics/hours/by-employee", params={"teams": ""})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2  # both Alice and Bob


def test_dashboard_norm_work_accepts_teams_param(tc_client):
    """teams param accepted without error — 200 response."""
    resp = tc_client.get("/api/v1/analytics/dashboard/norm-work?year=2026&quarter=2&teams=TeamA")
    assert resp.status_code == 200


def test_dashboard_categories_accepts_teams_param(tc_client):
    resp = tc_client.get("/api/v1/analytics/dashboard/categories?year=2026&quarter=2&teams=TeamA")
    assert resp.status_code == 200


def test_dashboard_norm_work_reads_from_snapshot(tc_client, testclient_db_session):
    """norm-work plan_hours come from ScenarioNormSnapshot, not ResourceBaseService."""
    from datetime import datetime
    from app.models import PlanningScenario, MandatoryWorkType
    from app.models.scenario_norm_snapshot import ScenarioNormSnapshot
    from app.models.scenario_revision import ScenarioRevision

    db = testclient_db_session

    wt = MandatoryWorkType(
        id="wt-nw1", code="projects_nw", label="Проекты NW",
        is_active=True, sort_order=1, subtracts_from_pool=False,
    )
    db.add(wt)
    sc = PlanningScenario(
        id="sc-nw1", name="Q2 NW", quarter="Q2", year=2026,
        status="approved", team="TNW",
    )
    db.add(sc)
    db.flush()
    rev = ScenarioRevision(
        id="rev-nw1", scenario_id="sc-nw1", revision_number=1,
        approved_at=datetime.utcnow(),
    )
    db.add(rev)
    db.flush()
    # Snapshot: 3 months, 42h each = 126h total
    for month in [4, 5, 6]:
        db.add(ScenarioNormSnapshot(
            id=f"ns-nw-{month}", revision_id="rev-nw1",
            employee_id=None, employee_name="X", role="analyst",
            year=2026, month=month, work_type_id="wt-nw1",
            work_type_label="Проекты NW", norm_hours=42.0,
        ))
    db.commit()

    resp = tc_client.get("/api/v1/analytics/dashboard/norm-work?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    item = next((i for i in data["items"] if i["work_type_id"] == "wt-nw1"), None)
    assert item is not None
    assert item["plan_hours"] == 126.0  # 42 * 3 months
