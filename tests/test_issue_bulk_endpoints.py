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
