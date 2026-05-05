"""Tests for BacklogService — involvement + duration propagation from Issue."""

import pytest

from app.models import BacklogItem, Issue, Project
from app.services.backlog_service import BacklogService


@pytest.fixture
def proj(db_session):
    p = Project(
        id="bs-p1",
        jira_project_id="bs-p1-jira",
        key="BS",
        name="BS Test",
        is_active=True,
    )
    db_session.add(p)
    db_session.commit()
    return p


def _make_issue(db, proj, key, category="initiatives_rfa", **kwargs):
    i = Issue(
        id=key,
        jira_issue_id=f"jira-{key}",
        key=key,
        summary=f"Issue {key}",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category=category,
        **kwargs,
    )
    db.add(i)
    db.commit()
    return i


def test_sync_propagates_involvement_and_duration(db_session, proj):
    """BacklogService.sync_from_issue копирует involvement + duration из Issue."""
    issue = _make_issue(
        db_session,
        proj,
        "BS-1",
        involvement_analyst=0.6,
        involvement_dev=0.8,
        involvement_qa=0.5,
        involvement_launch=0.3,
        duration_analyst_days=5.0,
        duration_dev_days=10.0,
        duration_qa_days=3.0,
        duration_launch_days=2.0,
    )

    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    assert item is not None
    assert item.involvement_analyst == pytest.approx(0.6)
    assert item.involvement_dev == pytest.approx(0.8)
    assert item.involvement_qa == pytest.approx(0.5)
    assert item.involvement_launch == pytest.approx(0.3)
    assert item.duration_analyst_days == pytest.approx(5.0)
    assert item.duration_dev_days == pytest.approx(10.0)
    assert item.duration_qa_days == pytest.approx(3.0)
    assert item.duration_launch_days == pytest.approx(2.0)


def test_sync_propagates_null_involvement(db_session, proj):
    """Если у Issue involvement не задан — BacklogItem тоже получает None."""
    issue = _make_issue(db_session, proj, "BS-2")

    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    assert item is not None
    assert item.involvement_analyst is None
    assert item.duration_analyst_days is None


def test_sync_updates_existing_backlog_involvement(db_session, proj):
    """При повторном sync значения involvement обновляются."""
    issue = _make_issue(
        db_session,
        proj,
        "BS-3",
        involvement_analyst=0.4,
        duration_analyst_days=3.0,
    )

    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    assert item is not None
    assert item.involvement_analyst == pytest.approx(0.4)

    # Update Issue values and re-sync
    issue.involvement_analyst = 0.9
    issue.duration_analyst_days = 7.0
    db_session.commit()

    item2 = svc.sync_from_issue(issue)
    db_session.commit()

    assert item2 is not None
    assert item2.id == item.id
    assert item2.involvement_analyst == pytest.approx(0.9)
    assert item2.duration_analyst_days == pytest.approx(7.0)
