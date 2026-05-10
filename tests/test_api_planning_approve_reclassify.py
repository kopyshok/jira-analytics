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


def test_draft_scenario_filters_by_category_only(client, seeded):
    """Draft scenario allocations include всё initiatives_rfa, в т.ч. под Эпиками.
    quarterly_tasks отсекаются (до approve)."""
    r = client.post("/api/v1/planning/scenarios", json={"name": "Q3", "year": 2026, "quarter": 3})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")
    assert r.status_code == 200, r.text
    allocs = r.json()

    item_ids = [a["backlog_item_id"] for a in allocs]
    assert "b-rfa" in item_ids, "root initiatives_rfa must be shown"
    assert "b-qrt" not in item_ids, "already-quarterly must be excluded"
    assert "b-child" in item_ids, (
        "initiatives_rfa with a parent (e.g. под Эпиком) must be shown — "
        "категория решает, а не наличие parent_id"
    )


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


def test_approve_reclassifies_included_issues(client, seeded, testclient_db_session):
    """Approving a scenario reclassifies included initiatives_rfa → quarterly_tasks."""
    db = testclient_db_session

    # Create draft scenario — only b-rfa shown (filter from Task 2)
    r = client.post("/api/v1/planning/scenarios", json={"name": "Q3", "year": 2026, "quarter": 3})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    # Mark b-rfa as included
    allocs_r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")
    alloc_id = next(a["id"] for a in allocs_r.json() if a["backlog_item_id"] == "b-rfa")
    r = client.patch(f"/api/v1/planning/scenarios/{sid}/allocations/{alloc_id}", json={"included": True})
    assert r.status_code == 200, r.text

    # Approve
    r = client.post(f"/api/v1/planning/scenarios/{sid}/approve")
    assert r.status_code == 200, r.text

    # Check issue category changed
    from app.models import Issue
    db.expire_all()
    issue = db.query(Issue).filter_by(id="i-rfa").one()
    assert issue.assigned_category == "quarterly_tasks"
    assert issue.category == "quarterly_tasks"


def test_approve_does_not_reclassify_excluded_issues(client, seeded, testclient_db_session):
    """Issues not included (included_flag=False) must NOT be reclassified on approve."""
    db = testclient_db_session

    # Create draft scenario — b-rfa auto-added with included_flag=False
    r = client.post("/api/v1/planning/scenarios", json={"name": "Q3 B", "year": 2026, "quarter": 3})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    # Approve WITHOUT marking b-rfa as included
    r = client.post(f"/api/v1/planning/scenarios/{sid}/approve")
    assert r.status_code == 200, r.text

    from app.models import Issue
    db.expire_all()
    issue = db.query(Issue).filter_by(id="i-rfa").one()
    assert issue.category == "initiatives_rfa", "excluded issue must not be reclassified"


def test_approve_removes_included_from_other_drafts(client, seeded, testclient_db_session):
    """After approval, reclassified items must be removed from other draft scenarios."""
    db = testclient_db_session
    from app.models import ScenarioAllocation

    # Create two draft scenarios — both get b-rfa
    r1 = client.post("/api/v1/planning/scenarios", json={"name": "Q3 A", "year": 2026, "quarter": 3})
    sid1 = r1.json()["id"]
    r2 = client.post("/api/v1/planning/scenarios", json={"name": "Q3 B", "year": 2026, "quarter": 3})
    sid2 = r2.json()["id"]

    # Mark b-rfa as included in scenario 1
    allocs_r = client.get(f"/api/v1/planning/scenarios/{sid1}/allocations")
    alloc_id = next(a["id"] for a in allocs_r.json() if a["backlog_item_id"] == "b-rfa")
    client.patch(f"/api/v1/planning/scenarios/{sid1}/allocations/{alloc_id}", json={"included": True})

    # Approve scenario 1
    r = client.post(f"/api/v1/planning/scenarios/{sid1}/approve")
    assert r.status_code == 200, r.text

    # b-rfa must no longer be in scenario 2's allocations
    db.expire_all()
    alloc_in_s2 = (
        db.query(ScenarioAllocation)
        .filter_by(scenario_id=sid2, backlog_item_id="b-rfa")
        .one_or_none()
    )
    assert alloc_in_s2 is None, "reclassified item must be removed from other draft scenarios"
