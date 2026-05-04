import pytest
import respx
import httpx
from app.connectors.confluence_client import ConfluenceClient, ConfluenceClientError


@pytest.mark.asyncio
@respx.mock
async def test_get_page_content_returns_html_body():
    respx.get("https://example.atlassian.net/wiki/rest/api/content/12345").mock(
        return_value=httpx.Response(200, json={
            "id": "12345",
            "title": "ТЗ Анализ себестоимости",
            "body": {"storage": {"value": "<p>Полный текст ТЗ</p>", "representation": "storage"}},
        })
    )
    async with ConfluenceClient(
        base_url="https://example.atlassian.net",
        email="x@y.z", api_token="t",
    ) as c:
        page = await c.get_page("12345")
    assert page.id == "12345"
    assert page.title == "ТЗ Анализ себестоимости"
    assert "Полный текст ТЗ" in page.body_html


@pytest.mark.asyncio
@respx.mock
async def test_resolve_tinyurl_follows_redirect():
    respx.get("https://example.atlassian.net/wiki/x/abc123").mock(
        return_value=httpx.Response(302, headers={"Location": "/wiki/spaces/PR/pages/98765/Title"})
    )
    async with ConfluenceClient(
        base_url="https://example.atlassian.net",
        email="x@y.z", api_token="t",
    ) as c:
        page_id = await c.resolve_tinyurl("https://example.atlassian.net/wiki/x/abc123")
    assert page_id == "98765"


@pytest.mark.asyncio
@respx.mock
async def test_get_page_404_raises():
    respx.get("https://example.atlassian.net/wiki/rest/api/content/missing").mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    async with ConfluenceClient(
        base_url="https://example.atlassian.net",
        email="x@y.z", api_token="t",
    ) as c:
        with pytest.raises(ConfluenceClientError):
            await c.get_page("missing")
