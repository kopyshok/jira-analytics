"""Manual backlog ideas (issue_id IS NULL) must respect the global team filter
via their own ``team`` field, not via the linked issue (which they lack).

Regression: a manually-created idea had no team and was filtered out entirely
because the team filter required ``Issue.team in (...)`` and a manual idea has
no linked issue.
"""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.services.event_bus import get_event_bus


def _make_client(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: AsyncMock()
    return TestClient(app)


def _teardown():
    app.dependency_overrides.clear()


def test_manual_item_visible_under_matching_team(testclient_db_session):
    from app.models import BacklogItem

    db = testclient_db_session
    db.add(BacklogItem(id="bi-t1", title="Manual T1", issue_id=None, team="T1"))
    db.commit()

    client = _make_client(db)
    try:
        resp = client.get("/api/v1/backlog?view=active&teams=T1")
        assert resp.status_code == 200, resp.text
        ids = [i["id"] for i in resp.json()]
        assert "bi-t1" in ids
    finally:
        _teardown()


def test_manual_item_hidden_under_other_team(testclient_db_session):
    from app.models import BacklogItem

    db = testclient_db_session
    db.add(BacklogItem(id="bi-t1b", title="Manual T1", issue_id=None, team="T1"))
    db.commit()

    client = _make_client(db)
    try:
        resp = client.get("/api/v1/backlog?view=active&teams=T2")
        assert resp.status_code == 200, resp.text
        ids = [i["id"] for i in resp.json()]
        assert "bi-t1b" not in ids
    finally:
        _teardown()


def test_manual_item_without_team_always_visible(testclient_db_session):
    """Teamless manual idea must never vanish behind a team filter."""
    from app.models import BacklogItem

    db = testclient_db_session
    db.add(BacklogItem(id="bi-noteam", title="Teamless manual", issue_id=None, team=None))
    db.commit()

    client = _make_client(db)
    try:
        resp = client.get("/api/v1/backlog?view=active&teams=T2")
        assert resp.status_code == 200, resp.text
        ids = [i["id"] for i in resp.json()]
        assert "bi-noteam" in ids
    finally:
        _teardown()


def test_create_manual_item_with_team(testclient_db_session):
    db = testclient_db_session
    client = _make_client(db)
    try:
        resp = client.post("/api/v1/backlog", json={"title": "New idea", "team": "T3"})
        assert resp.status_code == 201, resp.text
        assert resp.json()["team"] == "T3"
    finally:
        _teardown()
