"""POST /issues/{id}/plan/conflict-resolve + GET /plan-conflicts."""
import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Issue, Project, PlanAudit


def _project(db, key="CR"):
    p = Project(id=f"p-{key}", key=key, jira_project_id=f"jp-{key}", name=f"Project {key}")
    db.add(p)
    db.flush()
    return p


def _issue(db, project, key, **kwargs):
    i = Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}",
        summary=f"Summary {key}", issue_type="Task",
        status="Open", project_id=project.id, **kwargs,
    )
    db.add(i)
    db.flush()
    return i


def _audit(db, issue, role, value_before, value_after, source, **kw):
    a = PlanAudit(
        issue_id=issue.id, role=role,
        value_before=value_before, value_after=value_after,
        source=source, created_at=datetime.utcnow(), **kw,
    )
    db.add(a)
    db.flush()
    return a


@pytest.fixture
def client(testclient_db_session):
    def _override():
        yield testclient_db_session
    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def test_conflict_accept_jira(client, testclient_db_session):
    db = testclient_db_session
    p = _project(db)
    issue = _issue(db, p, "CR-1",
                   planned_dev_hours_jira=550,
                   planned_dev_hours_manual=600)
    _audit(db, issue, "dev", 500, 550, "jira_sync_conflict")
    db.commit()

    r = client.post(
        f"/api/v1/issues/{issue.id}/plan/conflict-resolve",
        json={"action": "accept_jira", "role": "dev"},
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    refreshed = db.query(Issue).filter_by(id=issue.id).one()
    assert refreshed.planned_dev_hours_manual is None
    assert refreshed.planned_dev_hours == 550


def test_conflict_ignore(client, testclient_db_session):
    db = testclient_db_session
    p = _project(db, key="CR2")
    issue = _issue(db, p, "CR-2",
                   planned_dev_hours_jira=550,
                   planned_dev_hours_manual=600)
    _audit(db, issue, "dev", 500, 550, "jira_sync_conflict")
    db.commit()

    r = client.post(
        f"/api/v1/issues/{issue.id}/plan/conflict-resolve",
        json={"action": "ignore", "role": "dev"},
    )
    assert r.status_code == 200

    db.expire_all()
    refreshed = db.query(Issue).filter_by(id=issue.id).one()
    assert refreshed.planned_dev_hours_manual == 600

    rows = db.query(PlanAudit).filter_by(issue_id=issue.id, role="dev").order_by(PlanAudit.created_at).all()
    assert rows[-1].source == "conflict_ignored"


def test_open_conflicts_lists_unresolved(client, testclient_db_session):
    db = testclient_db_session
    p = _project(db, key="CR3")
    issue = _issue(db, p, "CR-3", planned_dev_hours_jira=550, planned_dev_hours_manual=600)
    _audit(db, issue, "dev", 500, 550, "jira_sync_conflict")
    db.commit()

    r = client.get(f"/api/v1/issues/{issue.id}/plan-conflicts")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["role"] == "dev"
    assert body[0]["value_jira"] == 550


def test_open_conflicts_excludes_resolved(client, testclient_db_session):
    """Если после конфликта была запись accept_jira/ignore/manual_edit — не показываем."""
    import time
    db = testclient_db_session
    p = _project(db, key="CR4")
    issue = _issue(db, p, "CR-4", planned_dev_hours_jira=550, planned_dev_hours_manual=600)
    _audit(db, issue, "dev", 500, 550, "jira_sync_conflict")
    time.sleep(0.001)  # обеспечить order_by по created_at
    _audit(db, issue, "dev", 600, 550, "conflict_accepted")
    db.commit()

    r = client.get(f"/api/v1/issues/{issue.id}/plan-conflicts")
    assert r.status_code == 200
    assert r.json() == []


def test_conflict_404(client):
    r = client.post(
        "/api/v1/issues/nonexistent/plan/conflict-resolve",
        json={"action": "accept_jira", "role": "dev"},
    )
    assert r.status_code == 404
