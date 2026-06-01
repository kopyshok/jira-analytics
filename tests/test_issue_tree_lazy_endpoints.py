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


def test_tree_roots_skips_in_team_tasks_under_foreign_parent(client, db):
    """owned-by-team: in-team задача под чужим эпиком не показывается."""
    p = _mk_proj(db, "OWN")
    # Чужой эпик (другая команда) — не попадёт в primary_only выборку для A
    _mk_issue(db, p, "OWN-1", team="B", assigned_category="dev")
    # In-team задача с parent=чужой эпик — должна быть скрыта
    _mk_issue(db, p, "OWN-2", team="A", parent_id="i-OWN-1",
              assigned_category=None, category_verified=False)
    # In-team root — единственная в дереве
    _mk_issue(db, p, "OWN-3", team="A",
              assigned_category=None, category_verified=False)
    db.commit()
    try:
        resp = client.get("/api/v1/issues/tree/roots", params={
            "project_keys": "OWN", "teams": "A", "tab": "stack",
        })
        assert resp.status_code == 200
        keys = sorted([n["key"] for n in resp.json()])
        assert keys == ["OWN-3"], f"Ожидалось только OWN-3, получено {keys}"

        counts = client.get("/api/v1/issues/tree/counts", params={
            "project_keys": "OWN", "teams": "A",
        }).json()
        assert counts["stack"] == 1
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_tree_roots_skips_participating_only_tasks(client, db):
    """primary_only: задачи, где команда только в participating_teams,
    не подтягиваются — их разбирает продуктовая команда."""
    p = _mk_proj(db, "PRI")
    # Продуктовая задача команды A в stack
    _mk_issue(db, p, "PRI-1", team="A",
              assigned_category=None, category_verified=False)
    # Задача команды B, где A только участвует — НЕ должна попасть в выборку A
    import json as _json
    _mk_issue(db, p, "PRI-2", team="B",
              participating_teams=_json.dumps(["A"]),
              assigned_category=None, category_verified=False)
    db.commit()
    try:
        resp = client.get("/api/v1/issues/tree/roots", params={
            "project_keys": "PRI", "teams": "A", "tab": "stack",
        })
        assert resp.status_code == 200
        keys = sorted([n["key"] for n in resp.json()])
        assert keys == ["PRI-1"], f"Ожидалось только PRI-1, получено {keys}"

        resp_counts = client.get("/api/v1/issues/tree/counts", params={
            "project_keys": "PRI", "teams": "A",
        })
        assert resp_counts.json()["stack"] == 1
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


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


def test_tree_roots_returns_matching_for_stack_tab(client, db):
    p = _mk_proj(db, "RTS")
    epic = _mk_issue(db, p, "RTS-1", issue_type="Epic", assigned_category="dev")
    child = _mk_issue(db, p, "RTS-2", parent_id=epic.id,
                      assigned_category=None, category_verified=False)
    _mk_issue(db, p, "RTS-3", assigned_category=None, category_verified=False)
    _mk_issue(db, p, "RTS-4", assigned_category="dev")
    db.commit()
    try:
        resp = client.get("/api/v1/issues/tree/roots", params={
            "project_keys": "RTS", "tab": "stack",
        })
        assert resp.status_code == 200, resp.text
        items = resp.json()
        keys = sorted([n["key"] for n in items])
        assert "RTS-1" in keys
        assert "RTS-3" in keys
        epic_node = next(n for n in items if n["key"] == "RTS-1")
        assert epic_node["has_children"] is True
        assert epic_node["descendant_match_count"] >= 1
        single = next(n for n in items if n["key"] == "RTS-3")
        assert single["has_children"] is False
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_tree_roots_supports_search(client, db):
    p = _mk_proj(db, "SRC")
    _mk_issue(db, p, "SRC-1", summary="оплата заказа",
              assigned_category=None, category_verified=False)
    _mk_issue(db, p, "SRC-2", summary="отгрузка товара",
              assigned_category=None, category_verified=False)
    db.commit()
    try:
        resp = client.get("/api/v1/issues/tree/roots", params={
            "project_keys": "SRC", "tab": "stack", "search": "оплат",
        })
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["key"] == "SRC-1"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_epic_candidates_returns_epics_with_assigned_and_children(client, db):
    p = _mk_proj(db, "EPC")
    e1 = _mk_issue(db, p, "EPC-1", issue_type="Epic", assigned_category="dev")
    _mk_issue(db, p, "EPC-2", parent_id=e1.id, assigned_category=None, category_verified=False)
    e2 = _mk_issue(db, p, "EPC-3", issue_type="Epic", assigned_category=None)
    _mk_issue(db, p, "EPC-4", parent_id=e2.id)
    _mk_issue(db, p, "EPC-5", issue_type="Epic", assigned_category="dev")
    db.commit()
    try:
        resp = client.get("/api/v1/issues/tree/epic-candidates", params={"project_keys": "EPC"})
        assert resp.status_code == 200
        items = resp.json()
        keys = sorted([n["key"] for n in items])
        assert keys == ["EPC-1"]
        cand = items[0]
        assert cand["assigned_category"] == "dev"
        assert cand["summary"] == "EPC-1"
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()


def test_children_endpoint_filters_by_tab(client, db):
    p = _mk_proj(db, "CHL")
    epic = _mk_issue(db, p, "CHL-1", issue_type="Epic", assigned_category="dev")
    _mk_issue(db, p, "CHL-2", parent_id=epic.id,
              assigned_category=None, category_verified=False)  # stack
    _mk_issue(db, p, "CHL-3", parent_id=epic.id,
              assigned_category="dev")  # active (через свою dev)
    _mk_issue(db, p, "CHL-4", parent_id=epic.id,
              assigned_category="archive")  # archive
    db.commit()
    try:
        resp_stack = client.get(f"/api/v1/issues/{epic.id}/children", params={"tab": "stack"})
        assert resp_stack.status_code == 200
        keys = sorted([n["key"] for n in resp_stack.json()])
        assert keys == ["CHL-2"]

        resp_archive = client.get(f"/api/v1/issues/{epic.id}/children", params={"tab": "archive"})
        keys = sorted([n["key"] for n in resp_archive.json()])
        assert keys == ["CHL-4"]

        # Без tab — все дети
        resp_all = client.get(f"/api/v1/issues/{epic.id}/children")
        keys = sorted([n["key"] for n in resp_all.json()])
        assert keys == ["CHL-2", "CHL-3", "CHL-4"]
    finally:
        db.query(Issue).filter(Issue.project_id == p.id).delete()
        db.query(Project).filter(Project.id == p.id).delete()
        db.commit()
