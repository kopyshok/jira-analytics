"""API: GET /issues/{id}/hours-breakdown."""
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Issue, Project


def _project(db, key="HB"):
    p = Project(id=f"p-{key}", key=key, jira_project_id=f"jp-{key}", name=f"Project {key}")
    db.add(p)
    db.flush()
    return p


def _issue(db, project, key, **kwargs):
    i = Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}",
        summary=f"Summary {key}", issue_type=kwargs.pop("issue_type", "Task"),
        status="Open", project_id=project.id, **kwargs,
    )
    db.add(i)
    db.flush()
    return i


def _make_client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _teardown():
    app.dependency_overrides.pop(get_db, None)


def test_hours_breakdown_api(testclient_db_session):
    db = testclient_db_session
    p = _project(db)
    rfa = _issue(db, p, "RFA-API-10", issue_type="RFA",
                 planned_dev_hours_jira=500)
    db.commit()

    client = _make_client(db)
    try:
        r = client.get(f"/api/v1/issues/{rfa.id}/hours-breakdown", params={"year": 2026, "quarter": 2})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["plan"]["dev"] == 500
        assert body["plan"]["total"] == 500
        assert body["planable"]["dev"] == 500
        assert "flags" in body
    finally:
        _teardown()


def test_hours_breakdown_404(testclient_db_session):
    client = _make_client(testclient_db_session)
    try:
        r = client.get("/api/v1/issues/nonexistent-id/hours-breakdown", params={"year": 2026, "quarter": 2})
        assert r.status_code == 404
    finally:
        _teardown()


def test_hours_breakdown_invalid_quarter(testclient_db_session):
    db = testclient_db_session
    p = _project(db, key="HB2")
    rfa = _issue(db, p, "RFA-VAL-1", issue_type="RFA", planned_dev_hours_jira=100)
    db.commit()

    client = _make_client(db)
    try:
        r = client.get(f"/api/v1/issues/{rfa.id}/hours-breakdown", params={"year": 2026, "quarter": 99})
        assert r.status_code == 422
    finally:
        _teardown()
