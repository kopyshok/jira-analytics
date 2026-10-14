"""Настройки Confluence: свой адрес и токен, проверка подключения по сохранённым."""
import httpx
import respx
from fastapi.testclient import TestClient

from app.api.endpoints import settings as settings_ep
from app.database import get_db
from app.main import app
from app.models.app_setting import AppSetting


def test_confluence_settings_saved(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        empty = client.get("/api/v1/settings/confluence").json()
        put = client.put(
            "/api/v1/settings/confluence",
            json={"base_url": "confluence.example.test", "api_token": "tok"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert empty == {"base_url": None, "has_token": False}
    assert put.status_code == 200
    assert put.json() == {"base_url": "https://confluence.example.test", "has_token": True}


@respx.mock
async def test_confluence_test_uses_saved_settings(db_session):
    db_session.add_all([
        AppSetting(key="confluence_base_url", value="https://confluence.example.test"),
        AppSetting(key="confluence_api_token", value="tok"),
    ])
    db_session.commit()
    route = respx.get("https://confluence.example.test/rest/api/user/current").mock(
        return_value=httpx.Response(200, json={"username": "user_1", "displayName": "Сотрудник 1"})
    )
    result = await settings_ep.test_confluence_connection(db=db_session)
    assert result.connected is True
    assert result.user_name == "Сотрудник 1"
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"


async def test_confluence_test_without_settings(db_session):
    result = await settings_ep.test_confluence_connection(db=db_session)
    assert result.connected is False
    assert result.error


@respx.mock
async def test_confluence_test_non_json_answer(db_session):
    """Вместо данных — страница входа: понятная ошибка, а не сбой сервера."""
    db_session.add_all([
        AppSetting(key="confluence_base_url", value="https://confluence.example.test"),
        AppSetting(key="confluence_api_token", value="tok"),
    ])
    db_session.commit()
    respx.get("https://confluence.example.test/rest/api/user/current").mock(
        return_value=httpx.Response(200, text="<html>SSO</html>")
    )
    result = await settings_ep.test_confluence_connection(db=db_session)
    assert result.connected is False
    assert "Confluence" in result.error and "адрес" in result.error
