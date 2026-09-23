"""Список бэклога: спорные оценки."""
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, Issue, Project
from app.services.event_bus import get_event_bus
from app.services.plan_sources import candidates_from_json, fingerprint

SOURCES = {
    "dev": [
        {"source": "customfield_12432", "label": "Разработка (ч)", "value": 100.0},
        {"source": "sum", "label": "Оценка Back + Оценка Front", "value": 80.0},
    ],
    "qa": [{"source": "customfield_12433", "label": "Тестирование (ч)", "value": 20.0}],
}


def _get(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: AsyncMock()
    try:
        r = TestClient(app).get("/api/v1/backlog?view=active")
        assert r.status_code == 200, r.text
        return next(x for x in r.json() if x["id"] == "b-bd")
    finally:
        app.dependency_overrides.clear()


def _seed(db, choice=None):
    p = Project(id="p-bd", key="BD", jira_project_id="jp-bd", name="BD", is_active=True)
    i = Issue(
        id="i-bd", key="BD-1", jira_issue_id="j-bd", summary="S", issue_type="RFA",
        status="Open", status_category="new", project_id=p.id,
        planned_hours_sources=SOURCES, planned_hours_choice=choice,
    )
    b = BacklogItem(id="b-bd", title="S", issue_id=i.id)
    db.add_all([p, i, b])
    db.commit()


def test_disputed_role_and_candidates(testclient_db_session):
    _seed(testclient_db_session)
    row = _get(testclient_db_session)
    assert row["disputed_roles"] == ["dev"]
    assert row["estimate_candidates"]["dev"] == [
        {"source": "customfield_12432", "label": "Разработка (ч)", "value": 100.0},
        {"source": "sum", "label": "Оценка Back + Оценка Front", "value": 80.0},
    ]
    assert "qa" not in row["estimate_candidates"]


def test_valid_choice_hides_dispute(testclient_db_session):
    fp = fingerprint(candidates_from_json(SOURCES["dev"]))
    _seed(testclient_db_session, choice={"dev": {"source": "sum", "fingerprint": fp}})
    row = _get(testclient_db_session)
    assert row["disputed_roles"] == []
    assert row["estimate_candidates"] == {}


def test_child_row_carries_disputes(testclient_db_session):
    """Дочерний эпик RFA: спор виден в дочерней строке родителя."""
    db = testclient_db_session
    p = Project(id="p-bd", key="BD", jira_project_id="jp-bd", name="BD", is_active=True)
    parent = Issue(
        id="i-bd", key="BD-1", jira_issue_id="j-bd", summary="S", issue_type="RFA",
        status="Open", status_category="new", project_id=p.id,
    )
    child = Issue(
        id="i-bd-e", key="BD-2", jira_issue_id="j-bd-e", summary="E", issue_type="Эпик",
        status="Open", status_category="new", project_id=p.id, parent_id="i-bd",
        planned_hours_sources=SOURCES,
    )
    db.add_all([p, parent, child])
    db.flush()
    db.add_all([
        BacklogItem(id="b-bd", title="S", issue_id="i-bd"),
        BacklogItem(id="b-bd-e", title="E", issue_id="i-bd-e"),
    ])
    db.commit()

    row = _get(db)
    assert row["disputed_roles"] == []
    kid = next(c for c in row["children"] if c["id"] == "b-bd-e")
    assert kid["disputed_roles"] == ["dev"]
    assert [c["source"] for c in kid["estimate_candidates"]["dev"]] == ["customfield_12432", "sum"]
