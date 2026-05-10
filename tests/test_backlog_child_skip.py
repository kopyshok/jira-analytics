"""BacklogService: child issues with tracked category MUST be added to draft scenarios.

Initiatives often live under container Epics (e.g. AD-4400) — parent_id is set
but the issue is still a legitimate initiative. Категория решает.
"""

import pytest

from app.models import BacklogItem, Issue, PlanningScenario, Project, ScenarioAllocation
from app.services.backlog_service import BacklogService


@pytest.fixture
def proj(db_session):
    p = Project(id="bcs-p1", jira_project_id="bcs-p1-jira", key="BCS", name="BCS Test", is_active=True)
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def draft_scenario(db_session):
    s = PlanningScenario(id="bcs-s1", name="Q3 Test", year=2026, quarter=3, status="draft")
    db_session.add(s)
    db_session.commit()
    return s


def _make_issue(db, proj, key, parent_id=None, category="initiatives_rfa"):
    i = Issue(
        id=key,
        jira_issue_id=f"jira-{key}",
        key=key,
        summary=f"Issue {key}",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category=category,
        parent_id=parent_id,
    )
    db.add(i)
    db.commit()
    return i


def test_child_issue_with_tracked_category_added_to_draft_scenario(db_session, proj, draft_scenario):
    """Initiative under an Epic parent must still get a ScenarioAllocation."""
    parent = _make_issue(db_session, proj, "BCS-1")
    child = _make_issue(db_session, proj, "BCS-2", parent_id=parent.id)

    svc = BacklogService(db_session)
    result = svc.sync_from_issue(child)
    db_session.commit()

    assert result is not None  # BacklogItem created
    allocs = db_session.query(ScenarioAllocation).filter_by(backlog_item_id=result.id).all()
    assert len(allocs) == 1
    assert allocs[0].scenario_id == draft_scenario.id


def test_root_issue_added_to_draft_scenario(db_session, proj, draft_scenario):
    root = _make_issue(db_session, proj, "BCS-3")

    svc = BacklogService(db_session)
    result = svc.sync_from_issue(root)
    db_session.commit()

    assert result is not None
    allocs = db_session.query(ScenarioAllocation).filter_by(backlog_item_id=result.id).all()
    assert len(allocs) == 1
    assert allocs[0].scenario_id == draft_scenario.id
