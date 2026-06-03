"""GET /api/v1/backlog/ возвращает hierarchy-флаги для UI раскрытия RFA-строки."""
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


def test_backlog_list_includes_hierarchy_flags(client, testclient_db_session):
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
    # ответ может быть list или {items: [...]}; адаптируйся под реальный формат при необходимости
    if isinstance(rows, dict) and "items" in rows:
        rows = rows["items"]
    by_key = {row.get("issue_key") or row.get("jira_key"): row for row in rows if row.get("issue_key") or row.get("jira_key")}

    rfa_row = by_key.get("RFA-100")
    epic_row = by_key.get("PRJ-100")
    assert rfa_row is not None
    assert epic_row is not None

    # planning_mode по умолчанию whole
    assert rfa_row["planning_mode"] == "whole"
    assert rfa_row["included_in_planning"] is True

    # RFA — родитель Эпика
    assert rfa_row["has_children_in_backlog"] is True
    assert rfa_row["has_parent_in_backlog"] is False
    # Эпик — дочка RFA
    assert epic_row["has_parent_in_backlog"] is True
    assert epic_row["has_children_in_backlog"] is False


def test_backlog_flags_default_for_orphan(client, testclient_db_session):
    """Одиночная задача без родителя и без детей в backlog."""
    db = testclient_db_session
    p = _project(db, key="ORPH")
    issue = _issue(db, p, "ORPH-1")
    _backlog_item(db, issue)
    db.commit()

    r = client.get("/api/v1/backlog/")
    rows = r.json()
    if isinstance(rows, dict) and "items" in rows:
        rows = rows["items"]
    by_key = {row.get("issue_key") or row.get("jira_key"): row for row in rows if row.get("issue_key") or row.get("jira_key")}

    orph = by_key.get("ORPH-1")
    assert orph is not None
    assert orph["planning_mode"] == "whole"
    assert orph["included_in_planning"] is True
    assert orph["has_parent_in_backlog"] is False
    assert orph["has_children_in_backlog"] is False
