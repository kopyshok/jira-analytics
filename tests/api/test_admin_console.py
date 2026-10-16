"""Консоль Jira/Confluence: доступ, запуск, история."""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.app_setting import AppSetting
from app.models.console_run import ConsoleRun
from app.models.user import User, UserRole
from app.services import console_service as cs

URL = "/api/v1/admin/console"


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def jira_settings(testclient_db_session):
    testclient_db_session.add(AppSetting(key="jira_base_url", value="https://jira.example.ru"))
    testclient_db_session.add(AppSetting(key="jira_api_token", value="t"))
    testclient_db_session.commit()


@pytest.fixture
def fake_execute(monkeypatch):
    calls = []

    async def fake(lines, target, mask, base, token, **kw):
        calls.append((lines, target, mask, base, token))
        return cs.RunResult(output="=== Jira ===\nok\n", request_count=1,
                            error_count=0, rejected_count=0, duration_ms=5)

    monkeypatch.setattr(cs, "execute", fake)
    return calls


@pytest.mark.no_auth_bypass
def test_only_admin(testclient_db_session):
    email = f"console_{uuid.uuid4().hex[:8]}@example.com"
    testclient_db_session.add(User(id=str(uuid.uuid4()), email=email,
                                   password_hash=hash_password("pass123"),
                                   display_name="Менеджер", role=UserRole.manager))
    testclient_db_session.commit()
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    try:
        c = TestClient(app)
        token = c.post("/api/v1/auth/login", json={"email": email, "password": "pass123"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert c.get(f"{URL}/runs", headers=headers).status_code == 403
        assert c.post(f"{URL}/run", headers=headers,
                      json={"target": "jira", "text": "/rest/api/2/field"}).status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_run_saves_history(client, jira_settings, fake_execute):
    r = client.post(f"{URL}/run", json={"target": "jira", "text": "# x\n/rest/api/2/field", "mask": True})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["output_text"] == "=== Jira ===\nok\n"
    assert run["first_line"] == "/rest/api/2/field"
    assert run["user_name"] == "Test User" and run["masked"] is True
    assert run["created_at"].endswith("Z")
    assert fake_execute[0][1:] == ("jira", True, "https://jira.example.ru", "t")

    items = client.get(f"{URL}/runs").json()["items"]
    assert [i["id"] for i in items] == [run["id"]]
    assert "output_text" not in items[0]

    full = client.get(f"{URL}/runs/{run['id']}").json()
    assert full["input_text"] == "# x\n/rest/api/2/field"

    assert client.delete(f"{URL}/runs/{run['id']}").status_code == 204
    assert client.get(f"{URL}/runs/{run['id']}").status_code == 404


def test_run_without_settings_is_400(client, fake_execute):
    r = client.post(f"{URL}/run", json={"target": "confluence", "text": "/rest/api/space"})
    assert r.status_code == 400
    assert "Подключение к Confluence" in r.json()["detail"]
    assert fake_execute == []


def test_keeps_last_30_runs(client, jira_settings, fake_execute, testclient_db_session):
    old = datetime.utcnow() - timedelta(days=1)
    for i in range(30):
        testclient_db_session.add(ConsoleRun(
            target="jira", input_text=f"/rest/{i}", output_text="", user_name="x",
            created_at=old + timedelta(minutes=i), updated_at=old,
        ))
    testclient_db_session.commit()

    new_id = client.post(f"{URL}/run", json={"target": "jira", "text": "/rest/api/2/field"}).json()["id"]
    items = client.get(f"{URL}/runs").json()["items"]
    assert len(items) == 30
    assert items[0]["id"] == new_id
    assert "/rest/0" not in [i["first_line"] for i in items]
