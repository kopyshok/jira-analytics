"""Tests for BacklogService.sync_from_issue — auto-populate backlog from
Issue with category='initiatives_rfa' («Инициативы и RFA»)."""

import pytest

from app.models import BacklogItem, Issue, Project


@pytest.fixture
def proj(db_session):
    p = Project(
        id="p1",
        jira_project_id="p1-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    db_session.add(p)
    db_session.commit()
    return p


def _make_issue(db, proj, key, category, **planned):
    i = Issue(
        id=key,
        jira_issue_id=f"jira-{key}",
        key=key,
        summary=f"Epic {key}",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category=category,
        **planned,
    )
    db.add(i)
    db.commit()
    return i


def test_sync_creates_backlog_item_when_category_matches(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(
        db_session,
        proj,
        "RFA-1",
        "initiatives_rfa",
        planned_analyst_hours=40,
        planned_dev_hours=40,
        planned_qa_hours=20,
        planned_opo_hours=20,
        impact="high",
        risk="medium",
    )
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    assert item is not None
    assert item.issue_id == issue.id
    assert item.title == "Epic RFA-1"
    assert item.project_id == proj.id
    assert item.estimate_analyst_hours == 40
    assert item.estimate_dev_hours == 40
    assert item.estimate_qa_hours == 20
    assert item.estimate_opo_hours == 20
    assert item.estimate_hours == 120  # sum
    assert item.impact == "high"
    assert item.risk == "medium"
    assert item.opo_analyst_ratio == 0.5  # default


def test_sync_updates_existing_backlog_item(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(
        db_session,
        proj,
        "RFA-2",
        "initiatives_rfa",
        planned_analyst_hours=10,
        planned_dev_hours=10,
        planned_qa_hours=0,
        planned_opo_hours=0,
    )
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()
    assert item.estimate_hours == 20

    issue.planned_dev_hours = 50
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    db_session.refresh(item)
    assert item.estimate_dev_hours == 50
    assert item.estimate_hours == 60


def test_sync_preserves_local_fields(db_session, proj):
    """priority, opo_analyst_ratio — locals, Jira sync does not overwrite."""
    from app.services.backlog_service import BacklogService

    issue = _make_issue(
        db_session,
        proj,
        "RFA-3",
        "initiatives_rfa",
        planned_opo_hours=10,
    )
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    item.priority = 5
    item.opo_analyst_ratio = 0.7
    db_session.commit()

    svc.sync_from_issue(issue)
    db_session.commit()
    db_session.refresh(item)
    assert item.priority == 5
    assert item.opo_analyst_ratio == 0.7


def test_sync_deletes_item_when_category_changes_away(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-4", "initiatives_rfa")
    svc = BacklogService(db_session)
    svc.sync_from_issue(issue)
    db_session.commit()
    assert db_session.query(BacklogItem).filter_by(issue_id=issue.id).count() == 1

    issue.category = "development"
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    assert db_session.query(BacklogItem).filter_by(issue_id=issue.id).count() == 0


def test_sync_soft_unlinks_item_referenced_in_scenario(db_session, proj):
    from app.models import PlanningScenario, ScenarioAllocation
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-5", "initiatives_rfa")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    scenario = PlanningScenario(id="s1", name="Q2 draft", year=2026, quarter="Q2")
    db_session.add(scenario)
    db_session.add(
        ScenarioAllocation(
            id="a1",
            scenario_id=scenario.id,
            backlog_item_id=item.id,
            included_flag=True,
            planned_hours=0,
        )
    )
    db_session.commit()

    issue.category = None
    db_session.commit()
    svc.sync_from_issue(issue)
    db_session.commit()
    db_session.refresh(item)
    assert item.issue_id is None
    assert item.id is not None  # not deleted


def test_sync_ignores_issue_without_backlog_category(db_session, proj):
    from app.services.backlog_service import BacklogService

    issue = _make_issue(db_session, proj, "RFA-6", "development")
    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()
    assert item is None
    assert db_session.query(BacklogItem).filter_by(issue_id=issue.id).count() == 0
