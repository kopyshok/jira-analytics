"""Тесты ленивых tree-эндпоинтов для CategoriesEditorPage."""
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


def _mk_proj(db, key="LZY"):
    p = Project(id=f"proj-{key}", key=key, name=key, jira_project_id=f"j-{key}")
    db.add(p); db.flush()
    return p


def _mk_issue(db, proj, key, **overrides):
    defaults = dict(
        id=f"i-{key}", key=key, summary=key,
        issue_type="Task", status="Открыто",
        project_id=proj.id, jira_issue_id=f"j-{key}",
        category_verified=True, include_in_analysis=True,
    )
    defaults.update(overrides)
    i = Issue(**defaults); db.add(i); db.flush()
    return i


def test_tree_counts_groups_by_tab(client, db):
    p = _mk_proj(db, "CNT")
    _mk_issue(db, p, "CNT-1", assigned_category=None, category_verified=False)  # stack
    _mk_issue(db, p, "CNT-2", assigned_category="dev")  # active
    _mk_issue(db, p, "CNT-3", assigned_category="initiatives_rfa")  # initiatives
    _mk_issue(db, p, "CNT-4", assigned_category="archive_target")  # archive_target
    _mk_issue(db, p, "CNT-5", assigned_category="archive")  # archive
    db.commit()
    try:
        resp = client.get("/api/v1/issues/tree/counts", params={"project_keys": "CNT"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["stack"] == 1
        assert data["active"] == 1
        assert data["initiatives"] == 1
        assert data["archive_target"] == 1
        assert data["archive"] == 1
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()
