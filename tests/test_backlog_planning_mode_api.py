"""PATCH /backlog/{id}/planning-mode + /included."""
import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, Issue, Project


def _project(db, key="BPM"):
    p = Project(id=f"p-{key}", key=key, jira_project_id=f"jp-{key}", name=f"Project {key}")
    db.add(p)
    db.flush()
    return p


def _issue(db, project, key, **kwargs):
    i = Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}",
        summary=f"S {key}", issue_type=kwargs.pop("issue_type", "Task"),
        status="Open", project_id=project.id, **kwargs,
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


def test_set_planning_mode_to_by_epics(client, testclient_db_session):
    db = testclient_db_session
    p = _project(db)
    issue = _issue(db, p, "BPM-1", issue_type="RFA")
    bi = _backlog_item(db, issue)
    db.commit()

    r = client.patch(f"/api/v1/backlog/{bi.id}/planning-mode", json={"mode": "by_epics"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["planning_mode"] == "by_epics"

    db.expire_all()
    refreshed = db.query(BacklogItem).filter_by(id=bi.id).one()
    assert refreshed.planning_mode == "by_epics"


def test_set_planning_mode_back_to_whole(client, testclient_db_session):
    db = testclient_db_session
    p = _project(db)
    issue = _issue(db, p, "BPM-2", issue_type="RFA")
    bi = _backlog_item(db, issue, planning_mode="by_epics")
    db.commit()

    r = client.patch(f"/api/v1/backlog/{bi.id}/planning-mode", json={"mode": "whole"})
    assert r.status_code == 200
    db.expire_all()
    refreshed = db.query(BacklogItem).filter_by(id=bi.id).one()
    assert refreshed.planning_mode == "whole"


def test_set_included_false(client, testclient_db_session):
    db = testclient_db_session
    p = _project(db)
    issue = _issue(db, p, "BPM-3")
    bi = _backlog_item(db, issue)
    db.commit()

    r = client.patch(f"/api/v1/backlog/{bi.id}/included", json={"included": False})
    assert r.status_code == 200
    body = r.json()
    assert body["included_in_planning"] is False

    db.expire_all()
    refreshed = db.query(BacklogItem).filter_by(id=bi.id).one()
    assert refreshed.included_in_planning is False


def test_invalid_mode_rejected(client, testclient_db_session):
    db = testclient_db_session
    p = _project(db)
    issue = _issue(db, p, "BPM-4")
    bi = _backlog_item(db, issue)
    db.commit()

    r = client.patch(f"/api/v1/backlog/{bi.id}/planning-mode", json={"mode": "bogus"})
    assert r.status_code == 422


def test_planning_mode_404(client):
    r = client.patch("/api/v1/backlog/nonexistent/planning-mode", json={"mode": "whole"})
    assert r.status_code == 404


def test_included_404(client):
    r = client.patch("/api/v1/backlog/nonexistent/included", json={"included": True})
    assert r.status_code == 404
