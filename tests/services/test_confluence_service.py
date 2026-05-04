import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.services.confluence_service import (
    extract_confluence_urls,
    html_to_text,
    parse_page_id,
    ConfluenceService,
)


def test_extract_confluence_urls_basic():
    text = "См ТЗ https://itgri.atlassian.net/wiki/spaces/PR/pages/12345/Title и tinyurl https://itgri.atlassian.net/wiki/x/abcDEF"
    urls = extract_confluence_urls(text, "https://itgri.atlassian.net")
    assert "https://itgri.atlassian.net/wiki/spaces/PR/pages/12345/Title" in urls
    assert "https://itgri.atlassian.net/wiki/x/abcDEF" in urls


def test_extract_confluence_urls_dedup_and_skip_other_hosts():
    text = "https://other.atlassian.net/wiki/spaces/X/pages/1/T https://itgri.atlassian.net/wiki/spaces/X/pages/2/T https://itgri.atlassian.net/wiki/spaces/X/pages/2/T"
    urls = extract_confluence_urls(text, "https://itgri.atlassian.net")
    assert urls == ["https://itgri.atlassian.net/wiki/spaces/X/pages/2/T"]


def test_html_to_text_strips_tags():
    html = "<h1>Заголовок</h1><p>Параграф <b>жирный</b></p><ul><li>пункт</li></ul>"
    text = html_to_text(html)
    assert "Заголовок" in text
    assert "жирный" in text
    assert "пункт" in text
    assert "<" not in text


def test_parse_page_id_from_pages_url():
    assert parse_page_id("https://itgri.atlassian.net/wiki/spaces/PR/pages/12345/Title") == "12345"
    assert parse_page_id("https://itgri.atlassian.net/wiki/x/abcDEF") is None  # tinyurl needs resolve


@pytest.mark.asyncio
async def test_service_returns_cached_when_fresh(db_session):
    from app.models.confluence_page_cache import ConfluencePageCache
    from app.models.app_setting import AppSetting
    db_session.add(AppSetting(key="jira_base_url", value="https://itgri.atlassian.net"))
    db_session.add(AppSetting(key="jira_email", value="x@y.z"))
    db_session.add(AppSetting(key="jira_api_token", value="t"))
    db_session.add(ConfluencePageCache(
        page_id="12345",
        source_url="https://itgri.atlassian.net/wiki/spaces/X/pages/12345/T",
        title="Cached", body_text="cached body", error=None,
        fetched_at=datetime.utcnow() - timedelta(days=1),
    ))
    db_session.commit()

    svc = ConfluenceService(db_session)
    pages = await svc.fetch_pages(
        ["https://itgri.atlassian.net/wiki/spaces/X/pages/12345/T"]
    )
    assert len(pages) == 1
    assert pages[0].body_text == "cached body"


@pytest.mark.asyncio
async def test_service_refetches_when_stale(db_session):
    from app.models.confluence_page_cache import ConfluencePageCache
    from app.models.app_setting import AppSetting
    db_session.add(AppSetting(key="jira_base_url", value="https://itgri.atlassian.net"))
    db_session.add(AppSetting(key="jira_email", value="x@y.z"))
    db_session.add(AppSetting(key="jira_api_token", value="t"))
    db_session.add(ConfluencePageCache(
        page_id="99",
        source_url="https://itgri.atlassian.net/wiki/spaces/X/pages/99/T",
        title="Old", body_text="old body", error=None,
        fetched_at=datetime.utcnow() - timedelta(days=10),
    ))
    db_session.commit()

    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.get_page.return_value = type("P", (), {
        "id": "99", "title": "Fresh", "body_html": "<p>fresh</p>",
    })()

    with patch("app.services.confluence_service.ConfluenceClient.from_db", return_value=fake_client):
        svc = ConfluenceService(db_session)
        pages = await svc.fetch_pages(
            ["https://itgri.atlassian.net/wiki/spaces/X/pages/99/T"]
        )
    assert pages[0].body_text.strip() == "fresh"
