"""Тесты bulk-эндпоинтов для массового разбора задач."""
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import Issue, Project


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mk_project(db, key="BULK", name="Bulk Test"):
    p = Project(
        id=f"proj-{key}",
        key=key,
        name=name,
        jira_project_id=f"jira-{key}",
    )
    db.add(p)
    db.flush()
    return p


def _mk_issue(db, project, key, **overrides):
    defaults = dict(
        id=f"issue-{key}",
        key=key,
        summary=f"Summary {key}",
        issue_type="Task",
        status="Открыто",
        project_id=project.id,
        jira_issue_id=f"jira-{key}",
        category_verified=False,
        include_in_analysis=True,
    )
    defaults.update(overrides)
    i = Issue(**defaults)
    db.add(i)
    db.flush()
    return i


def test_bulk_preview_returns_filtered_issues(client, db):
    p = _mk_project(db)
    old_dt = datetime.now(timezone.utc) - timedelta(days=400)
    _mk_issue(db, p, "BULK-1", status="Закрыто", status_changed_at=old_dt.replace(tzinfo=None))
    _mk_issue(db, p, "BULK-2", status="Открыто")
    db.commit()

    try:
        resp = client.post("/api/v1/issues/bulk/preview", json={
            "filters": {
                "project_keys": ["BULK"],
                "statuses": ["Закрыто"],
            },
            "limit": 100,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 1
        assert data["truncated"] is False
        assert len(data["items"]) == 1
        assert data["items"][0]["key"] == "BULK-1"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_bulk_archive_applies_to_matching(client, db):
    p = _mk_project(db, key="ARC")
    _mk_issue(db, p, "ARC-1", status="Закрыто", include_in_analysis=True)
    _mk_issue(db, p, "ARC-2", status="Закрыто", include_in_analysis=True)
    _mk_issue(db, p, "ARC-3", status="Открыто", include_in_analysis=True)
    db.commit()
    try:
        resp = client.post("/api/v1/issues/bulk/archive", json={
            "filters": {"project_keys": ["ARC"], "statuses": ["Закрыто"]},
            "category_code": "archive",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["updated"] == 2
        assert sorted(data["archived_ids"]) == sorted(["issue-ARC-1", "issue-ARC-2"])

        db.expire_all()
        i1 = db.get(Issue, "issue-ARC-1")
        i3 = db.get(Issue, "issue-ARC-3")
        assert i1.assigned_category == "archive"
        assert i1.include_in_analysis is False
        assert i3.assigned_category is None
        assert i3.include_in_analysis is True
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_bulk_archive_rejects_non_archive_code(client, db):
    resp = client.post("/api/v1/issues/bulk/archive", json={
        "filters": {"project_keys": ["ARC"]},
        "category_code": "support",
    })
    assert resp.status_code == 400
    assert "архивн" in resp.json()["detail"].lower()


def test_bulk_accept_suggestions_writes_derived_into_assigned(client, db):
    p = _mk_project(db, key="SUG")
    _mk_issue(db, p, "SUG-1",
              category="support",
              assigned_category=None,
              category_verified=False)
    _mk_issue(db, p, "SUG-2",
              category=None,
              assigned_category=None,
              category_verified=False)
    _mk_issue(db, p, "SUG-3",
              category="support",
              assigned_category="dev",
              category_verified=True)
    db.commit()
    try:
        resp = client.post("/api/v1/issues/bulk/accept-suggestions", json={
            "filters": {"project_keys": ["SUG"], "only_no_assigned": True},
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["applied"] == 1
        assert data["skipped_no_suggestion"] == 1

        db.expire_all()
        assert db.get(Issue, "issue-SUG-1").assigned_category == "support"
        assert db.get(Issue, "issue-SUG-1").category_verified is True
        assert db.get(Issue, "issue-SUG-2").assigned_category is None
        assert db.get(Issue, "issue-SUG-3").assigned_category == "dev"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()
