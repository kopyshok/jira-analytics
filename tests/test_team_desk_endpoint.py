"""Эндпоинты рабочего стола тимлида."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Issue, Project


@pytest.fixture()
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _issue(db) -> Issue:
    project = Project(
        id=str(uuid.uuid4()),
        jira_project_id=str(uuid.uuid4()),
        key=f"OS{uuid.uuid4().hex[:4]}",
        name="OS",
    )
    db.add(project)
    db.flush()
    row = Issue(
        id=str(uuid.uuid4()),
        jira_issue_id=str(uuid.uuid4()),
        key="OS-1",
        summary="Задача",
        issue_type="Задача",
        status="В РАБОТЕ",
        project_id=project.id,
    )
    db.add(row)
    db.commit()
    return row


def test_overview_empty_without_filters(client):
    resp = client.get("/api/v1/team-desk/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["developers"] == []
    assert body["issues"] == []


def test_settings_roundtrip(client):
    resp = client.get("/api/v1/team-desk/settings")
    assert resp.status_code == 200
    cfg = resp.json()
    assert cfg["thresholds"]["decomposition_hours"] == 16

    cfg["thresholds"]["decomposition_hours"] = 24
    resp = client.put("/api/v1/team-desk/settings", json=cfg)
    assert resp.status_code == 200
    assert resp.json()["thresholds"]["decomposition_hours"] == 24


def test_flag_dictionary(client):
    resp = client.get("/api/v1/team-desk/flags")
    assert resp.status_code == 200
    codes = [item["code"] for item in resp.json()]
    assert codes[0] == "over"
    assert "stale" in codes


def test_mark_and_unmark(client, testclient_db_session):
    issue = _issue(testclient_db_session)

    resp = client.post(
        f"/api/v1/team-desk/issues/{issue.id}/mark",
        json={"flag": "stale", "signature": "В РАБОТЕ", "comment": "ждём заказчика"},
    )
    assert resp.status_code == 200
    assert resp.json()["flag"] == "stale"

    resp = client.delete(f"/api/v1/team-desk/issues/{issue.id}/mark?flag=stale")
    assert resp.status_code == 200


def test_mark_rejects_unknown_flag(client, testclient_db_session):
    issue = _issue(testclient_db_session)

    resp = client.post(
        f"/api/v1/team-desk/issues/{issue.id}/mark",
        json={"flag": "выдуманный", "signature": "x"},
    )
    assert resp.status_code == 422
