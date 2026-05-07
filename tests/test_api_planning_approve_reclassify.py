"""Tests: draft scenario allocation filter + approval category reclassification."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def seeded(testclient_db_session):
    """Seed: project + 3 issues (root rfa, already-quarterly, child rfa) + backlog items."""
    from app.models import BacklogItem, Issue, Project
    db = testclient_db_session

    proj = Project(id="p1", jira_project_id="j-p1", key="PRJ", name="Test", is_active=True)
    db.add(proj)

    issue_rfa = Issue(
        id="i-rfa", jira_issue_id="j-rfa", key="PRJ-1", summary="Root RFA",
        issue_type="RFA", status="Open", project_id="p1",
        category="initiatives_rfa", assigned_category="initiatives_rfa", parent_id=None,
    )
    issue_qrt = Issue(
        id="i-qrt", jira_issue_id="j-qrt", key="PRJ-2", summary="Already Quarterly",
        issue_type="Task", status="Open", project_id="p1",
        category="quarterly_tasks", assigned_category="quarterly_tasks", parent_id=None,
    )
    issue_child = Issue(
        id="i-child", jira_issue_id="j-child", key="PRJ-3", summary="Child Task",
        issue_type="Task", status="Open", project_id="p1",
        category="initiatives_rfa", assigned_category=None, parent_id="i-rfa",
    )
    db.add_all([issue_rfa, issue_qrt, issue_child])

    item_rfa = BacklogItem(id="b-rfa", title="Root RFA", issue_id="i-rfa")
    item_qrt = BacklogItem(id="b-qrt", title="Already Quarterly", issue_id="i-qrt")
    item_child = BacklogItem(id="b-child", title="Child Task", issue_id="i-child")
    db.add_all([item_rfa, item_qrt, item_child])
    db.commit()


def test_draft_scenario_filters_non_rfa_and_children(client, seeded):
    """Draft scenario allocations must only include root initiatives_rfa items."""
    r = client.post("/api/v1/planning/scenarios", json={"name": "Q3", "year": 2026, "quarter": 3})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")
    assert r.status_code == 200, r.text
    allocs = r.json()

    item_ids = [a["backlog_item_id"] for a in allocs]
    assert "b-rfa" in item_ids, "root initiatives_rfa must be shown"
    assert "b-qrt" not in item_ids, "already-quarterly must be excluded"
    assert "b-child" not in item_ids, "child issue must be excluded"


def test_approved_scenario_shows_all_items(client, seeded, testclient_db_session):
    """Approved scenario must return all allocations — no filter applied."""
    from app.models import PlanningScenario, ScenarioAllocation
    from app.models.base import generate_uuid
    db = testclient_db_session

    sid = generate_uuid()
    scenario = PlanningScenario(id=sid, name="Q2 Approved", year=2026, quarter=2, status="approved")
    db.add(scenario)
    db.add_all([
        ScenarioAllocation(scenario_id=sid, backlog_item_id="b-rfa", included_flag=True, planned_hours=0),
        ScenarioAllocation(scenario_id=sid, backlog_item_id="b-qrt", included_flag=True, planned_hours=0),
        ScenarioAllocation(scenario_id=sid, backlog_item_id="b-child", included_flag=False, planned_hours=0),
    ])
    db.commit()

    r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")
    assert r.status_code == 200, r.text
    allocs = r.json()
    item_ids = [a["backlog_item_id"] for a in allocs]
    assert "b-rfa" in item_ids
    assert "b-qrt" in item_ids
    assert "b-child" in item_ids
