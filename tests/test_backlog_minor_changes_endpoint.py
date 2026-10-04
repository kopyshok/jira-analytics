"""GET /backlog/minor-changes-summary — сводка минорных изменений по командам шапки."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Category, Issue, MandatoryWorkType, Project
from app.services.event_bus import get_event_bus


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: AsyncMock()
    return TestClient(app)


def _seed(db):
    wt = MandatoryWorkType(code="minor_change", label="Минорные изменения")
    db.add(wt)
    db.flush()
    db.add(Category(code="minor_change", label="Минорные", work_type_id=wt.id))
    p = Project(jira_project_id="p1", key="OS", name="OS")
    db.add(p)
    db.flush()
    for key, team in (("OS-1", "А"), ("OS-2", "Б")):
        db.add(Issue(
            jira_issue_id=f"j-{key}", key=key, summary=key, issue_type="Задача", status="В работе",
            status_category="indeterminate", project_id=p.id, team=team,
            assigned_category="minor_change", planned_dev_hours_jira=5,
        ))
    db.commit()


def test_summary_per_requested_team(testclient_db_session):
    _seed(testclient_db_session)
    client = _client(testclient_db_session)
    try:
        resp = client.get("/api/v1/backlog/minor-changes-summary?teams=Б,А")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [b["team"] for b in body["teams"]] == ["Б", "А"]
    assert body["teams"][0]["open_count"] == 1
    assert body["teams"][0]["hours"]["dev"] == 5.0
    assert body["teams"][0]["tasks"][0]["key"] == "OS-2"
    assert body["year"] >= 2026 and body["quarter"] in (1, 2, 3, 4)


def test_summary_without_teams_returns_all_teams_with_minor(testclient_db_session):
    _seed(testclient_db_session)
    client = _client(testclient_db_session)
    try:
        resp = client.get("/api/v1/backlog/minor-changes-summary")
    finally:
        app.dependency_overrides.clear()

    assert sorted(b["team"] for b in resp.json()["teams"]) == ["А", "Б"]
