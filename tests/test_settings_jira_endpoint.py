"""Настройки Jira: адрес и персональный токен, почта больше не нужна."""
import httpx
import pytest
import respx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.endpoints import settings as settings_ep
from app.database import get_db
from app.main import app
from tests.dc_fixtures import load_dc


def test_jira_settings_have_no_email(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        put = client.put("/api/v1/settings/jira", json={"base_url": "jira.example.test", "api_token": "tok"})
        got = client.get("/api/v1/settings/jira")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert put.status_code == 200
    assert got.json() == {"base_url": "https://jira.example.test", "has_token": True}


@respx.mock
async def test_jira_test_endpoint_uses_bearer_token():
    me = load_dc("user_search_single.json")[0]
    route = respx.get("https://jira.example.test/rest/api/2/myself").mock(
        return_value=httpx.Response(200, json=me)
    )
    result = await settings_ep.test_jira_credentials(
        settings_ep.JiraTestRequest(base_url="https://jira.example.test", api_token="tok")
    )
    assert result.connected is True
    assert result.user_name == me["displayName"]
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"


@respx.mock
async def test_jira_test_endpoint_requires_token():
    """Пустой токен не подменяется токеном из .env и не уходит на чужой адрес."""
    route = respx.route().mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(HTTPException) as exc:
        await settings_ep.test_jira_credentials(
            settings_ep.JiraTestRequest(base_url="https://other.example.test", api_token="  ")
        )
    assert exc.value.status_code == 400
    assert "токен" in exc.value.detail
    assert not route.called
