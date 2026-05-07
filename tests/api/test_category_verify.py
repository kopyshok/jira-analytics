"""Tests for POST /issues/{id}/verify endpoint."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.issue import Issue
from app.models.project import Project


@pytest.fixture
def db():
    import app.models  # noqa: F401 — register all models so Base.metadata is complete
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed(db):
    db.add(Project(id="p1", jira_project_id="J1", key="PRJ", name="Project"))
    epic = Issue(
        id="epic1", jira_issue_id="100", key="PRJ-100",
        summary="Epic", issue_type="Epic", status="To Do",
        project_id="p1", category_verified=False, require_child_verification=False,
    )
    child1 = Issue(
        id="ch1", jira_issue_id="101", key="PRJ-101",
        summary="Child 1", issue_type="Task", status="To Do",
        project_id="p1", parent_id="epic1", category_verified=False,
    )
    child2 = Issue(
        id="ch2", jira_issue_id="102", key="PRJ-102",
        summary="Child 2", issue_type="Task", status="To Do",
        project_id="p1", parent_id="epic1", category_verified=False,
    )
    grandchild = Issue(
        id="gc1", jira_issue_id="103", key="PRJ-103",
        summary="Grandchild", issue_type="Sub-task", status="To Do",
        project_id="p1", parent_id="ch1", category_verified=False,
    )
    already_verified = Issue(
        id="av1", jira_issue_id="104", key="PRJ-104",
        summary="Already verified", issue_type="Task", status="To Do",
        project_id="p1", parent_id="epic1", category_verified=True,
    )
    db.add_all([epic, child1, child2, grandchild, already_verified])
    db.commit()


def test_verify_single_issue(client, db):
    _seed(db)
    r = client.post("/api/v1/issues/ch1/verify", json={
        "cascade": False,
        "require_child_verification": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["verified_count"] == 1
    db.expire_all()
    assert db.get(Issue, "ch1").category_verified is True
    # ch2 and gc1 untouched
    assert db.get(Issue, "ch2").category_verified is False
    assert db.get(Issue, "gc1").category_verified is False


def test_verify_with_cascade(client, db):
    _seed(db)
    r = client.post("/api/v1/issues/epic1/verify", json={
        "cascade": True,
        "require_child_verification": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # epic + ch1 + ch2 + gc1 = 4 (av1 was already verified, skipped)
    assert body["verified_count"] == 4
    db.expire_all()
    for issue_id in ["epic1", "ch1", "ch2", "gc1"]:
        assert db.get(Issue, issue_id).category_verified is True


def test_verify_sets_require_child_verification(client, db):
    _seed(db)
    r = client.post("/api/v1/issues/epic1/verify", json={
        "cascade": False,
        "require_child_verification": True,
    })
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Issue, "epic1").require_child_verification is True


def test_verify_404_on_missing(client, db):
    _seed(db)
    r = client.post("/api/v1/issues/nonexistent/verify", json={
        "cascade": False,
        "require_child_verification": False,
    })
    assert r.status_code == 404
