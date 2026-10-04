"""Tests for BacklogService — duration propagation from Issue; involvement не из Jira."""

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


def test_sync_propagates_duration(db_session, proj):
    """BacklogService.sync_from_issue копирует длительности из Issue."""
    issue = _make_issue(
        db_session,
        proj,
        "BS-1",
        duration_analyst_days=5.0,
        duration_dev_days=10.0,
        duration_qa_days=3.0,
        duration_launch_days=2.0,
    )

    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    assert item is not None
    assert item.involvement_analyst is None
    assert item.duration_analyst_days == pytest.approx(5.0)
    assert item.duration_dev_days == pytest.approx(10.0)
    assert item.duration_qa_days == pytest.approx(3.0)
    assert item.duration_launch_days == pytest.approx(2.0)


def test_sync_propagates_null_duration(db_session, proj):
    """Если у Issue длительность не задана — BacklogItem тоже получает None."""
    issue = _make_issue(db_session, proj, "BS-2")

    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    assert item is not None
    assert item.involvement_analyst is None
    assert item.duration_analyst_days is None


def test_sync_updates_existing_backlog_duration(db_session, proj):
    """При повторном sync длительность обновляется."""
    issue = _make_issue(db_session, proj, "BS-3", duration_analyst_days=3.0)

    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    db_session.commit()

    issue.duration_analyst_days = 7.0
    db_session.commit()

    item2 = svc.sync_from_issue(issue)
    db_session.commit()

    assert item2 is not None
    assert item2.id == item.id
    assert item2.duration_analyst_days == pytest.approx(7.0)


def test_sync_keeps_fixed_involvement(db_session, proj):
    """Синхронизация не трогает вовлечённость, зафиксированную в фазе."""
    issue = _make_issue(db_session, proj, "BS-4")

    svc = BacklogService(db_session)
    item = svc.sync_from_issue(issue)
    item.involvement_dev = 0.5
    db_session.commit()

    item2 = svc.sync_from_issue(issue)
    db_session.commit()

    assert item2.involvement_dev == pytest.approx(0.5)
