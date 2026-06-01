"""Тесты helper для определения эффективной категории с учётом предков."""
import pytest
from app.database import SessionLocal
from app.models import Issue, Project
from app.services.category_resolver import CategoryResolver, effective_category_with_ancestors


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mk_proj(db, key):
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


def test_own_assigned_wins(db):
    p = _mk_proj(db, "EFF1")
    epic = _mk_issue(db, p, "EFF1-1", issue_type="Epic", assigned_category="support")
    child = _mk_issue(db, p, "EFF1-2", parent_id=epic.id, assigned_category="dev")
    db.commit()
    try:
        resolver = CategoryResolver(db)
        result = effective_category_with_ancestors(resolver, child, pending={})
        assert result == "dev"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_inherited_from_ancestor(db):
    p = _mk_proj(db, "EFF2")
    epic = _mk_issue(db, p, "EFF2-1", issue_type="Epic", assigned_category="support")
    child = _mk_issue(db, p, "EFF2-2", parent_id=epic.id, assigned_category=None)
    db.commit()
    try:
        resolver = CategoryResolver(db)
        result = effective_category_with_ancestors(resolver, child, pending={})
        assert result == "support"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_pending_overrides_assigned(db):
    p = _mk_proj(db, "EFF3")
    issue = _mk_issue(db, p, "EFF3-1", assigned_category="dev")
    db.commit()
    try:
        resolver = CategoryResolver(db)
        result = effective_category_with_ancestors(resolver, issue, pending={issue.id: "qa"})
        assert result == "qa"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_returns_none_for_unverified(db):
    p = _mk_proj(db, "EFF4")
    issue = _mk_issue(db, p, "EFF4-1", assigned_category=None, category_verified=False)
    db.commit()
    try:
        resolver = CategoryResolver(db)
        result = effective_category_with_ancestors(resolver, issue, pending={})
        assert result is None
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()
