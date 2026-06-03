"""GET /api/v1/backlog/ возвращает hierarchy-флаги + дочки скрыты из flat-списка."""
import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, Issue, Project


def _project(db, key="HBF"):
    p = Project(id=f"p-{key}", key=key, jira_project_id=f"jp-{key}", name=f"Project {key}")
    db.add(p)
    db.flush()
    return p


def _issue(db, project, key, **kwargs):
    i = Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}",
        summary=f"S {key}", issue_type=kwargs.pop("issue_type", "Task"),
        status="Open", project_id=project.id, category="initiatives_rfa", **kwargs,
    )
    db.add(i)
    db.flush()
    return i


def _backlog_item(db, issue, **kwargs):
    bi = BacklogItem(id=f"bi-{issue.key}", issue_id=issue.id, title=issue.summary, **kwargs)
    db.add(bi)
    db.flush()
    return bi


@pytest.fixture
def client(testclient_db_session):
    def _override():
        yield testclient_db_session
    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def test_child_hidden_from_flat_list_visible_in_parent_children(client, testclient_db_session):
    """RFA-1 + Epic-1 (child of RFA-1) → только RFA-1 в flat-списке, Epic-1 — в children."""
    db = testclient_db_session
    p = _project(db)
    rfa = _issue(db, p, "RFA-100", issue_type="RFA")
    epic = _issue(db, p, "PRJ-100", issue_type="Epic", parent_id=rfa.id)
    _backlog_item(db, rfa)
    _backlog_item(db, epic)
    db.commit()

    r = client.get("/api/v1/backlog/")
    assert r.status_code == 200, r.text
    rows = r.json()
    if isinstance(rows, dict) and "items" in rows:
        rows = rows["items"]

    keys = {row.get("jira_key") for row in rows}

    # Дочка скрыта из flat-списка
    assert "PRJ-100" not in keys, "Epic (дочка) не должна быть в flat-списке"
    # Родитель виден
    assert "RFA-100" in keys

    rfa_row = next(r for r in rows if r.get("jira_key") == "RFA-100")
    assert rfa_row["has_children_in_backlog"] is True
    assert rfa_row["has_parent_in_backlog"] is False

    # Дочка видна через children родителя
    children = rfa_row.get("children", [])
    assert len(children) == 1
    c = children[0]
    assert c["key"] == "PRJ-100"
    assert c["issue_type"] == "Epic"
    assert c["included_in_planning"] is True
    assert "id" in c      # backlog_item.id нужен для PATCH
    assert "issue_id" in c


def test_orphan_has_empty_children(client, testclient_db_session):
    """Одиночная задача без родителя и без детей → children=[]."""
    db = testclient_db_session
    p = _project(db, key="ORPH")
    issue = _issue(db, p, "ORPH-1")
    _backlog_item(db, issue)
    db.commit()

    r = client.get("/api/v1/backlog/")
    rows = r.json()
    if isinstance(rows, dict) and "items" in rows:
        rows = rows["items"]
    by_key = {row.get("jira_key"): row for row in rows if row.get("jira_key")}

    orph = by_key.get("ORPH-1")
    assert orph is not None
    assert orph["planning_mode"] == "whole"
    assert orph["included_in_planning"] is True
    assert orph["has_parent_in_backlog"] is False
    assert orph["has_children_in_backlog"] is False
    assert orph.get("children", []) == []


def test_child_outside_backlog_stays_in_flat_list(client, testclient_db_session):
    """Задача с parent_id, чей родитель НЕ в backlog — остаётся в flat-списке."""
    db = testclient_db_session
    p = _project(db, key="EXT")
    # parent issue — есть в Issues, но нет в BacklogItem
    parent_issue = _issue(db, p, "EXT-0", issue_type="RFA")
    child_issue = _issue(db, p, "EXT-1", issue_type="Epic", parent_id=parent_issue.id)
    # только дочка в backlog
    _backlog_item(db, child_issue)
    db.commit()

    r = client.get("/api/v1/backlog/")
    rows = r.json()
    if isinstance(rows, dict) and "items" in rows:
        rows = rows["items"]
    by_key = {row.get("jira_key"): row for row in rows if row.get("jira_key")}

    # Дочка остаётся в flat-списке (её parent не в backlog)
    assert "EXT-1" in by_key
    assert by_key["EXT-1"]["has_parent_in_backlog"] is False


def test_multilevel_rfa_epic_subtask(client, testclient_db_session):
    """RFA → Epic → Subtask, все три в backlog.

    Ожидание: RFA в flat-списке; Epic в children RFA; Subtask скрыт из flat
    (его parent Epic тоже в backlog) — в соответствии со spec: multilevel
    depth=1, Subtask виден как child Epic но Epic уже не в flat.

    Текущая реализация: RFA видна, Epic — в её children (скрыта из flat),
    Subtask — тоже скрыта из flat (parent Epic в backlog), но в Epic.children.
    """
    db = testclient_db_session
    p = _project(db, key="MULTI")
    rfa = _issue(db, p, "MULTI-1", issue_type="RFA")
    epic = _issue(db, p, "MULTI-2", issue_type="Epic", parent_id=rfa.id)
    subtask = _issue(db, p, "MULTI-3", issue_type="Subtask", parent_id=epic.id)
    _backlog_item(db, rfa)
    _backlog_item(db, epic)
    _backlog_item(db, subtask)
    db.commit()

    r = client.get("/api/v1/backlog/")
    rows = r.json()
    if isinstance(rows, dict) and "items" in rows:
        rows = rows["items"]
    keys = {row.get("jira_key") for row in rows}

    # Только RFA в flat-списке
    assert "MULTI-1" in keys
    assert "MULTI-2" not in keys   # Epic — дочка RFA → скрыта
    assert "MULTI-3" not in keys   # Subtask — дочка Epic → тоже скрыта

    rfa_row = next(r for r in rows if r.get("jira_key") == "MULTI-1")
    rfa_children_keys = {c["key"] for c in rfa_row.get("children", [])}
    # Epic — прямой ребёнок RFA → в её children
    assert "MULTI-2" in rfa_children_keys
