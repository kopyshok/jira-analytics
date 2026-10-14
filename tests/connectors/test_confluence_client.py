"""Confluence Data Center: свой адрес, токен Bearer, пути без /wiki."""
import httpx
import pytest
import respx

from app.connectors.confluence_client import (
    ConfluenceClient,
    ConfluenceClientError,
    page_id_from_url,
)
from app.models.app_setting import AppSetting

BASE = "https://confluence.example.test"


def _client() -> ConfluenceClient:
    return ConfluenceClient(base_url=BASE, api_token="tok")


@respx.mock
async def test_get_page_uses_bearer_and_dc_path():
    route = respx.get(f"{BASE}/rest/api/content/12345").mock(
        return_value=httpx.Response(200, json={
            "id": "12345",
            "title": "ТЗ Анализ себестоимости",
            "body": {"storage": {"value": "<p>Полный текст ТЗ</p>", "representation": "storage"}},
        })
    )
    async with _client() as c:
        page = await c.get_page("12345")
    assert page.id == "12345"
    assert page.title == "ТЗ Анализ себестоимости"
    assert "Полный текст ТЗ" in page.body_html
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"
    assert dict(route.calls.last.request.url.params) == {"expand": "body.storage"}


@respx.mock
async def test_get_page_404_raises():
    respx.get(f"{BASE}/rest/api/content/missing").mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    async with _client() as c:
        with pytest.raises(ConfluenceClientError):
            await c.get_page("missing")


@respx.mock
async def test_tiny_link_follows_redirect_to_page_id():
    respx.get(f"{BASE}/x/AbCdE").mock(
        return_value=httpx.Response(302, headers={"Location": f"{BASE}/pages/viewpage.action?pageId=98765"})
    )
    async with _client() as c:
        assert await c.resolve_page_id(f"{BASE}/x/AbCdE") == "98765"


@respx.mock
async def test_display_link_is_found_by_title():
    route = respx.get(f"{BASE}/rest/api/content").mock(
        return_value=httpx.Response(200, json={"results": [{"id": "555", "title": "План работ"}]})
    )
    async with _client() as c:
        page_id = await c.resolve_page_id(
            f"{BASE}/display/PR/%D0%9F%D0%BB%D0%B0%D0%BD+%D1%80%D0%B0%D0%B1%D0%BE%D1%82"
        )
    assert page_id == "555"
    assert dict(route.calls.last.request.url.params) == {
        "spaceKey": "PR", "title": "План работ", "limit": "1",
    }


async def test_direct_page_id_needs_no_request():
    async with _client() as c:
        assert await c.resolve_page_id(f"{BASE}/pages/viewpage.action?pageId=42") == "42"
        assert await c.resolve_page_id(f"{BASE}/spaces/PR/pages/77/Title") == "77"
    assert page_id_from_url(f"{BASE}/x/AbCdE") is None


@respx.mock
async def test_current_user():
    respx.get(f"{BASE}/rest/api/user/current").mock(
        return_value=httpx.Response(200, json={"username": "user_1", "displayName": "Сотрудник 1"})
    )
    async with _client() as c:
        assert (await c.get_current_user())["displayName"] == "Сотрудник 1"


def test_from_db_uses_confluence_settings(db_session):
    db_session.add_all([
        AppSetting(key="confluence_base_url", value=BASE + "/"),
        AppSetting(key="confluence_api_token", value="tok"),
    ])
    db_session.commit()
    assert ConfluenceClient.from_db(db_session).base_url == BASE


def test_missing_settings_raise(db_session):
    with pytest.raises(ConfluenceClientError):
        ConfluenceClient.from_db(db_session)


@respx.mock
async def test_non_json_or_incomplete_answer_raises_client_error():
    """Страница входа/прокси с кодом 200 или ответ без id — ошибка клиента, не падение."""
    respx.get(f"{BASE}/rest/api/content/1").mock(
        return_value=httpx.Response(200, text="<html>Вход в систему</html>")
    )
    respx.get(f"{BASE}/rest/api/content/2").mock(
        return_value=httpx.Response(200, json={"title": "без id"})
    )
    respx.get(f"{BASE}/rest/api/user/current").mock(
        return_value=httpx.Response(200, text="<html>SSO</html>")
    )
    async with _client() as c:
        for call in (c.get_page("1"), c.get_page("2"), c.get_current_user()):
            with pytest.raises(ConfluenceClientError):
                await call


@respx.mock(assert_all_called=False)
async def test_tiny_link_redirect_to_foreign_host_is_not_followed(respx_mock):
    respx_mock.get(f"{BASE}/x/AbCdE").mock(
        return_value=httpx.Response(
            302, headers={"Location": "https://evil.example.test/display/PR/Title"}
        )
    )
    foreign = respx_mock.route(host="evil.example.test").mock(
        return_value=httpx.Response(200, json={"results": [{"id": "1"}]})
    )
    own_search = respx_mock.get(f"{BASE}/rest/api/content").mock(
        return_value=httpx.Response(200, json={"results": [{"id": "1"}]})
    )
    async with _client() as c:
        assert await c.resolve_page_id(f"{BASE}/x/AbCdE") is None
    assert not foreign.called
    assert not own_search.called


@respx.mock
async def test_tiny_link_without_redirect_gives_none():
    respx.get(f"{BASE}/x/Login").mock(return_value=httpx.Response(200, text="<html>SSO</html>"))
    respx.get(f"{BASE}/x/Gone").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/x/NoLoc").mock(return_value=httpx.Response(302))
    async with _client() as c:
        for code in ("Login", "Gone", "NoLoc"):
            assert await c.resolve_page_id(f"{BASE}/x/{code}") is None


@respx.mock
async def test_context_path_base_url():
    """Confluence под путём сервера: короткая ссылка → «красивая» → поиск по названию."""
    ctx = "https://wiki.example.test/confluence"
    respx.get(f"{ctx}/x/AbCdE").mock(
        return_value=httpx.Response(302, headers={"Location": "/confluence/display/PR/Plan+(draft)"})
    )
    search = respx.get(f"{ctx}/rest/api/content").mock(
        return_value=httpx.Response(200, json={"results": [{"id": "555"}]})
    )
    async with ConfluenceClient(base_url=ctx + "/", api_token="tok") as c:
        assert await c.resolve_page_id(f"{ctx}/x/AbCdE") == "555"
        # Тот же сервер с другим регистром и схемой — свой; соседний путь — чужой.
        assert await c.resolve_page_id("HTTP://WIKI.example.test/confluence/x/AbCdE") == "555"
        assert await c.resolve_page_id("https://wiki.example.test/confluence2/x/AbCdE") is None
    assert dict(search.calls.last.request.url.params) == {
        "spaceKey": "PR", "title": "Plan (draft)", "limit": "1",
    }
