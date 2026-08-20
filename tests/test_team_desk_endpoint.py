"""Эндпоинты рабочего стола тимлида."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Employee, EmployeeTeam, Issue, Project


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


def test_overview_keeps_only_developers(client, testclient_db_session):
    """Аналитик из той же команды в срез не попадает — раздел про разработчиков."""
    db = testclient_db_session
    project = Project(
        id=str(uuid.uuid4()),
        jira_project_id=str(uuid.uuid4()),
        key=f"OS{uuid.uuid4().hex[:4]}",
        name="OS",
    )
    db.add(project)
    db.flush()

    people = {}
    for account, name, role in (
        ("acc-dev", "Шутов Сергей", "dev"),
        ("acc-analyst", "Фокеева Наталья", "analyst"),
    ):
        emp = Employee(
            id=str(uuid.uuid4()),
            jira_account_id=account,
            display_name=name,
            role=role,
        )
        db.add(emp)
        db.flush()
        db.add(
            EmployeeTeam(
                id=str(uuid.uuid4()),
                employee_id=emp.id,
                team="Команда 1С",
                is_primary=True,
            )
        )
        people[account] = emp
        db.add(
            Issue(
                id=str(uuid.uuid4()),
                jira_issue_id=str(uuid.uuid4()),
                key=f"OS-{account}",
                summary="Задача",
                issue_type="Задача",
                status="В РАБОТЕ",
                project_id=project.id,
                developer_account_id=account,
                developer_display_name=name,
                dev_est_hours=8.0,
            )
        )
    db.commit()

    resp = client.get("/api/v1/team-desk/overview", params={"teams": "Команда 1С"})
    assert resp.status_code == 200
    body = resp.json()
    assert [d["developer_id"] for d in body["developers"]] == ["acc-dev"]
    assert [i["key"] for i in body["issues"]] == ["OS-acc-dev"]


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


def test_settings_disabled_flags_roundtrip(client):
    """Выключенный признак переживает сохранение; мусорные коды отсекаются."""
    cfg = client.get("/api/v1/team-desk/settings").json()
    assert cfg["disabled_flags"] == []

    cfg["disabled_flags"] = ["decomp", "такого признака нет"]
    body = client.put("/api/v1/team-desk/settings", json=cfg).json()
    assert body["disabled_flags"] == ["decomp"]
    assert client.get("/api/v1/team-desk/settings").json()["disabled_flags"] == ["decomp"]


def test_flag_dictionary(client):
    resp = client.get("/api/v1/team-desk/flags")
    assert resp.status_code == 200
    codes = [item["code"] for item in resp.json()]
    assert codes[0] == "over"
    assert "stale" in codes
    by_code = {item["code"]: item["threshold"] for item in resp.json()}
    assert by_code["decomp"] == "decomposition_hours"
    assert by_code["orphan"] is None


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


def test_daily_rate_set_and_clear(client, testclient_db_session):
    """Норму по «резиновой» задаче ставят и снимают одной ручкой."""
    issue = _issue(testclient_db_session)
    resp = client.put(
        f"/api/v1/team-desk/issues/{issue.id}/daily-rate", json={"hours": 2}
    )
    assert resp.status_code == 200
    assert resp.json()["hours"] == 2.0

    resp = client.put(
        f"/api/v1/team-desk/issues/{issue.id}/daily-rate", json={"hours": None}
    )
    assert resp.status_code == 200
    assert resp.json()["hours"] is None


def test_daily_rate_unknown_issue(client, testclient_db_session):
    resp = client.put(
        f"/api/v1/team-desk/issues/{uuid.uuid4()}/daily-rate", json={"hours": 2}
    )
    assert resp.status_code == 404
