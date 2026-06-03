"""PATCH /issues/{id}/plan + revert + history."""
import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Issue, Project, PlanAudit


def _project(db, key="PE"):
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


def _client_with_db(db_session):
    """TestClient с переопределённым get_db → db_session."""
    def _override():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client(testclient_db_session):
    yield from _client_with_db(testclient_db_session)


def test_patch_plan_creates_audit(client, testclient_db_session):
    db = testclient_db_session
    p = _project(db)
    issue = _issue(db, p, "PE-1", planned_dev_hours_jira=500)
    db.commit()

    r = client.patch(
        f"/api/v1/issues/{issue.id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "После ретро"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan"]["dev"] == 600

    rows = db.query(PlanAudit).filter_by(issue_id=issue.id).all()
    assert len(rows) == 1
    assert rows[0].role == "dev"
    assert rows[0].value_before == 500
    assert rows[0].value_after == 600
    assert rows[0].source == "manual_edit"
    assert rows[0].comment == "После ретро"


def test_patch_plan_requires_comment(client, testclient_db_session):
    db = testclient_db_session
    p = _project(db, key="PE2")
    issue = _issue(db, p, "PE-2", planned_dev_hours_jira=500)
    db.commit()

    r = client.patch(
        f"/api/v1/issues/{issue.id}/plan",
        json={"role_hours": {"dev": 600}, "comment": ""},
    )
    assert r.status_code == 422


def test_revert_plan(client, testclient_db_session):
    db = testclient_db_session
    p = _project(db, key="PE3")
    issue = _issue(db, p, "PE-3", planned_dev_hours_jira=500)
    db.commit()

    client.patch(
        f"/api/v1/issues/{issue.id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "test"},
    )
    r = client.post(f"/api/v1/issues/{issue.id}/plan/revert", json={})
    assert r.status_code == 200
    db.expire_all()
    refreshed = db.query(Issue).filter_by(id=issue.id).one()
    assert refreshed.planned_dev_hours_manual is None
    assert refreshed.planned_dev_hours == 500


def test_plan_history(client, testclient_db_session):
    db = testclient_db_session
    p = _project(db, key="PE4")
    issue = _issue(db, p, "PE-4", planned_dev_hours_jira=500)
    db.commit()

    client.patch(
        f"/api/v1/issues/{issue.id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "first"},
    )
    client.patch(
        f"/api/v1/issues/{issue.id}/plan",
        json={"role_hours": {"dev": 700}, "comment": "second"},
    )
    r = client.get(f"/api/v1/issues/{issue.id}/plan-history")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 2
    # latest first
    assert rows[0]["value_after"] == 700
    assert rows[0]["comment"] == "second"


def test_plan_history_404(client):
    r = client.get("/api/v1/issues/nonexistent-id/plan-history")
    assert r.status_code == 404
