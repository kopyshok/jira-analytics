"""Tests for /backlog/{id}/link-jira, /unlink-jira, /refresh-from-jira."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite with StaticPool for TestClient compatibility."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _override(db):
    app.dependency_overrides[get_db] = lambda: db


def test_link_jira_pulls_estimates_from_issue(db_session):
    from app.models import BacklogItem, Category, Issue, Project

    cat = Category(
        id="cat-ib",
        code="initiatives_rfa",
        label="Инициативы и RFA",
        color="#7F77DD",
        sort_order=22,
        is_system=True,
    )
    proj = Project(
        id="p1",
        jira_project_id="p1-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    issue = Issue(
        id="i1",
        jira_issue_id="i1-jira",
        key="RFA-42",
        summary="Real epic",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category="initiatives_rfa",
        planned_analyst_hours=8,
        planned_dev_hours=16,
        planned_qa_hours=4,
        planned_opo_hours=2,
    )
    manual = BacklogItem(
        id="m1",
        title="Manual idea",
        estimate_analyst_hours=1,
        estimate_hours=1,
        priority=3,
    )
    db_session.add_all([cat, proj, issue, manual])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(
            f"/api/v1/backlog/{manual.id}/link-jira",
            json={"jira_key": "RFA-42"},
        )
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(manual)
    assert manual.issue_id == issue.id
    assert manual.estimate_analyst_hours == 8
    assert manual.estimate_dev_hours == 16
    assert manual.estimate_qa_hours == 4
    assert manual.estimate_opo_hours == 2
    assert manual.estimate_hours == 30


def test_link_jira_unknown_key_returns_404(db_session):
    from app.models import BacklogItem

    manual = BacklogItem(id="m2", title="Idea")
    db_session.add(manual)
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(
            f"/api/v1/backlog/{manual.id}/link-jira",
            json={"jira_key": "NOPE-999"},
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_link_jira_already_linked_returns_409(db_session):
    """Если Issue уже привязана к другому BacklogItem, вторая привязка — 409."""
    from app.models import BacklogItem, Issue, Project

    proj = Project(
        id="p-409",
        jira_project_id="p-409-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    issue = Issue(
        id="i-409",
        jira_issue_id="i-409-jira",
        key="RFA-409",
        summary="X",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category="initiatives_rfa",
    )
    first = BacklogItem(id="m-first", title="First", issue_id=issue.id)
    second = BacklogItem(id="m-second", title="Second")
    db_session.add_all([proj, issue, first, second])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(
            f"/api/v1/backlog/{second.id}/link-jira",
            json={"jira_key": "RFA-409"},
        )
        assert r.status_code == 409, r.text
    finally:
        app.dependency_overrides.clear()


def test_unlink_jira_nulls_issue_id(db_session):
    from app.models import BacklogItem, Issue, Project

    proj = Project(
        id="p2",
        jira_project_id="p2-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    issue = Issue(
        id="i2",
        jira_issue_id="i2-jira",
        key="RFA-100",
        summary="X",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category="initiatives_rfa",
    )
    item = BacklogItem(
        id="m3",
        title="X",
        issue_id=issue.id,
        estimate_analyst_hours=10,
        estimate_hours=10,
    )
    db_session.add_all([proj, issue, item])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/backlog/{item.id}/unlink-jira")
        assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(item)
    assert item.issue_id is None
    # estimates retained (user may want to edit afterwards)
    assert item.estimate_analyst_hours == 10


def test_refresh_from_jira_pulls_all_matching(db_session):
    from app.models import BacklogItem, Category, Issue, Project

    cat = Category(
        id="cat-ib2",
        code="initiatives_rfa",
        label="Инициативы и RFA",
        color="#7F77DD",
        sort_order=22,
        is_system=True,
    )
    proj = Project(
        id="p3",
        jira_project_id="p3-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    db_session.add_all([cat, proj])
    for idx, (k, h) in enumerate([("RFA-1", 10), ("RFA-2", 20)]):
        db_session.add(
            Issue(
                id=f"i-refresh-{idx}",
                jira_issue_id=f"i-refresh-{idx}-jira",
                key=k,
                summary=k,
                issue_type="RFA",
                status="Open",
                project_id=proj.id,
                category="initiatives_rfa",
                planned_analyst_hours=h,
            )
        )
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post("/api/v1/backlog/refresh-from-jira")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == 2
    finally:
        app.dependency_overrides.clear()

    assert db_session.query(BacklogItem).count() == 2


def test_refresh_from_jira_removes_stale_items(db_session):
    """Если Issue потерял категорию — refresh убирает BacklogItem (или soft-unlinks)."""
    from app.models import BacklogItem, Issue, Project

    proj = Project(
        id="p-stale",
        jira_project_id="p-stale-jira",
        key="RFA",
        name="RFA",
        is_active=True,
    )
    issue = Issue(
        id="i-stale",
        jira_issue_id="i-stale-jira",
        key="RFA-STALE",
        summary="was backlog",
        issue_type="RFA",
        status="Open",
        project_id=proj.id,
        category="development",  # already moved away
    )
    # Old BacklogItem linked to issue that no longer matches.
    stale = BacklogItem(id="m-stale", title="stale", issue_id=issue.id)
    db_session.add_all([proj, issue, stale])
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post("/api/v1/backlog/refresh-from-jira")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["removed"] >= 1
    finally:
        app.dependency_overrides.clear()

    assert db_session.query(BacklogItem).filter_by(id="m-stale").count() == 0
