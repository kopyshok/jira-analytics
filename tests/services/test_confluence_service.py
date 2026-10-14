"""ConfluenceService на Confluence DC: ссылки по адресу из настроек, кэш, разрешение id."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.models.app_setting import AppSetting
from app.models.confluence_page_cache import ConfluencePageCache
from app.services.confluence_service import (
    ConfluenceService,
    extract_confluence_urls,
    html_to_text,
    parse_page_id,
)

BASE = "https://confluence.example.test"


def _settings(db):
    db.add(AppSetting(key="confluence_base_url", value=BASE))
    db.add(AppSetting(key="confluence_api_token", value="t"))


def test_extract_dc_links_inside_wiki_markup():
    text = (
        f"См. ТЗ [страница|{BASE}/pages/viewpage.action?pageId=12345] и {BASE}/x/AbCdE, "
        f"а также {BASE}/display/PR/План+работ и {BASE}/spaces/PR/pages/777/Title."
    )
    assert extract_confluence_urls(text, BASE) == [
        f"{BASE}/pages/viewpage.action?pageId=12345",
        f"{BASE}/x/AbCdE",
        f"{BASE}/display/PR/План+работ",
        f"{BASE}/spaces/PR/pages/777/Title",
    ]


def test_extract_skips_other_hosts_and_dedups():
    text = f"https://other.example.test/x/Zz {BASE}/x/AbCdE {BASE}/x/AbCdE"
    assert extract_confluence_urls(text, BASE) == [f"{BASE}/x/AbCdE"]


def test_extract_without_base_url():
    assert extract_confluence_urls(f"{BASE}/x/AbCdE", "") == []


def test_html_to_text_strips_tags():
    html = "<h1>Заголовок</h1><p>Параграф <b>жирный</b></p><ul><li>пункт</li></ul>"
    text = html_to_text(html)
    assert "Заголовок" in text
    assert "жирный" in text
    assert "пункт" in text
    assert "<" not in text


def test_parse_page_id():
    assert parse_page_id(f"{BASE}/pages/viewpage.action?pageId=12345") == "12345"
    assert parse_page_id(f"{BASE}/spaces/PR/pages/12345/Title") == "12345"
    assert parse_page_id(f"{BASE}/x/AbCdE") is None


async def test_service_returns_cached_when_fresh(db_session):
    _settings(db_session)
    url = f"{BASE}/pages/viewpage.action?pageId=12345"
    db_session.add(ConfluencePageCache(
        page_id="12345", source_url=url, title="Cached", body_text="cached body",
        error=None, fetched_at=datetime.utcnow() - timedelta(days=1),
    ))
    db_session.commit()

    pages = await ConfluenceService(db_session).fetch_pages([url])
    assert len(pages) == 1
    assert pages[0].body_text == "cached body"


async def test_service_refetches_when_stale(db_session):
    _settings(db_session)
    url = f"{BASE}/pages/viewpage.action?pageId=99"
    db_session.add(ConfluencePageCache(
        page_id="99", source_url=url, title="Old", body_text="old body",
        error=None, fetched_at=datetime.utcnow() - timedelta(days=10),
    ))
    db_session.commit()

    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.get_page.return_value = type("P", (), {
        "id": "99", "title": "Fresh", "body_html": "<p>fresh</p>",
    })()

    with patch("app.services.confluence_service.ConfluenceClient.from_db", return_value=fake_client):
        pages = await ConfluenceService(db_session).fetch_pages([url])
    assert pages[0].body_text.strip() == "fresh"


async def test_service_resolves_short_link_through_client(db_session):
    _settings(db_session)
    db_session.commit()
    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.resolve_page_id.return_value = "77"
    fake_client.get_page.return_value = type("P", (), {
        "id": "77", "title": "Короткая", "body_html": "<p>текст</p>",
    })()

    with patch("app.services.confluence_service.ConfluenceClient.from_db", return_value=fake_client):
        pages = await ConfluenceService(db_session).fetch_pages([f"{BASE}/x/AbCdE"])

    fake_client.resolve_page_id.assert_awaited_once_with(f"{BASE}/x/AbCdE")
    assert pages[0].page_id == "77"


async def test_service_without_token_returns_nothing(db_session):
    """Адрес Confluence есть, токена нет — саммари строится без страниц, без падения."""
    db_session.add(AppSetting(key="confluence_base_url", value=BASE))
    db_session.commit()

    pages = await ConfluenceService(db_session).fetch_pages(
        [f"{BASE}/pages/viewpage.action?pageId=1"]
    )
    assert pages == []


async def test_service_survives_unreachable_server(db_session):
    """Сервер Confluence недоступен — саммари строится без страниц, без падения."""
    import httpx

    _settings(db_session)
    db_session.commit()
    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.get_page.side_effect = httpx.ConnectError("нет связи")

    with patch("app.services.confluence_service.ConfluenceClient.from_db", return_value=fake_client):
        pages = await ConfluenceService(db_session).fetch_pages(
            [f"{BASE}/pages/viewpage.action?pageId=5"]
        )
    assert pages == []


def test_extract_host_case_scheme_parentheses_and_path_boundary():
    text = (
        f"(см. {BASE}/display/PR/План+(черновик)) и "
        "HTTP://CONFLUENCE.Example.Test/x/AbCdE, "
        f"а {BASE}evil/x/Zz и {BASE}.evil.test/x/Yy — чужие."
    )
    assert extract_confluence_urls(text, BASE + "/") == [
        f"{BASE}/display/PR/План+(черновик)",
        "HTTP://CONFLUENCE.Example.Test/x/AbCdE",
    ]


async def test_service_skips_non_json_page(db_session):
    """Вместо страницы пришла страница входа (код 200) — саммари без страниц, без падения."""
    import httpx
    import respx

    _settings(db_session)
    db_session.commit()
    with respx.mock:
        respx.get(f"{BASE}/rest/api/content/5").mock(
            return_value=httpx.Response(200, text="<html>Вход</html>")
        )
        pages = await ConfluenceService(db_session).fetch_pages(
            [f"{BASE}/pages/viewpage.action?pageId=5"]
        )
    assert pages == []


async def test_service_context_path_end_to_end(db_session):
    """Confluence под путём сервера: ссылки из текста → id → страницы."""
    import httpx
    import respx

    ctx = "https://wiki.example.test/confluence"
    db_session.add(AppSetting(key="confluence_base_url", value=ctx))
    db_session.add(AppSetting(key="confluence_api_token", value="t"))
    db_session.commit()
    text = (
        f"[ТЗ|{ctx}/x/AbCdE] и "
        "http://WIKI.example.test/confluence/pages/viewpage.action?pageId=12"
    )
    urls = extract_confluence_urls(text, ctx)

    def _page(pid: str) -> httpx.Response:
        return httpx.Response(200, json={
            "id": pid, "title": f"Стр {pid}", "body": {"storage": {"value": f"<p>текст {pid}</p>"}},
        })

    with respx.mock:
        respx.get(f"{ctx}/x/AbCdE").mock(
            return_value=httpx.Response(302, headers={"Location": f"{ctx}/display/PR/Plan"})
        )
        respx.get(f"{ctx}/rest/api/content").mock(
            return_value=httpx.Response(200, json={"results": [{"id": "555"}]})
        )
        respx.get(f"{ctx}/rest/api/content/555").mock(return_value=_page("555"))
        respx.get(f"{ctx}/rest/api/content/12").mock(return_value=_page("12"))
        pages = await ConfluenceService(db_session).fetch_pages(urls)

    assert len(urls) == 2
    assert sorted(p.page_id for p in pages) == ["12", "555"]
    assert all(p.body_text.startswith("текст") for p in pages)
