"""ConfluenceService — extract Confluence-ссылок, fetch с кэшем, html→text."""
import re
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.confluence_client import (
    ConfluenceClient,
    ConfluenceClientError,
    base_url_pattern,
    page_id_from_url,
)
from app.models.app_setting import AppSetting
from app.models.confluence_page_cache import ConfluencePageCache


logger = logging.getLogger("jira_analytics.confluence")

CACHE_TTL = timedelta(days=7)
MAX_BODY_CHARS = 8000  # обрезаем перед сохранением — лимит для промпта


@dataclass
class FetchedPage:
    page_id: str
    source_url: str
    title: str
    body_text: str


CONFLUENCE_BASE_URL_KEY = "confluence_base_url"

# Хвост ссылки на страницу Confluence DC после адреса сервера: прямой id,
# /spaces/…/pages/N, «красивая» /display/<пространство>/<название>, короткая
# /x/…. Описание в Jira DC — wiki-разметка, ссылка часто внутри [текст|адрес]:
# «|» и «]» завершают адрес. «)» в названии страницы допустима — непарную
# срезает _trim_url.
_LINK_TAIL = (
    r"(?:pages/viewpage\.action\?pageId=\d+"
    r"|spaces/[^\s/|\]]+/pages/\d+[^\s|\]]*"
    r"|display/[^\s/|\]]+/[^\s|\]]+"
    r"|x/[A-Za-z0-9_\-]+)"
)


def _trim_url(url: str) -> str:
    """Срезать хвостовую пунктуацию текста; «)» — только непарную."""
    while True:
        trimmed = url.rstrip(".,;")
        if trimmed.endswith(")") and trimmed.count("(") < trimmed.count(")"):
            trimmed = trimmed[:-1]
        if trimmed == url:
            return url
        url = trimmed


def extract_confluence_urls(text: Optional[str], base_url: str) -> list[str]:
    """Уникальные ссылки на страницы Confluence с адреса из настроек, в порядке появления."""
    if not text or not base_url:
        return []
    pattern = re.compile(base_url_pattern(base_url) + "/" + _LINK_TAIL)
    seen: set[str] = set()
    out: list[str] = []
    for m in pattern.finditer(text):
        url = _trim_url(m.group(0))
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def parse_page_id(url: str) -> Optional[str]:
    """id из ссылки с прямым id; короткую и «красивую» ссылки разрешает клиент."""
    return page_id_from_url(url)


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "br", "h1", "h2", "h3", "h4", "li", "div"}:
            self.parts.append("\n")


def html_to_text(html: str) -> str:
    if not html:
        return ""
    s = _Stripper()
    s.feed(html)
    text = "".join(s.parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class ConfluenceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _base_url(self) -> Optional[str]:
        row = self.db.query(AppSetting).filter(AppSetting.key == CONFLUENCE_BASE_URL_KEY).first()
        return row.value if row and row.value else None

    async def fetch_pages(self, urls: list[str]) -> list[FetchedPage]:
        """Для каждого URL вернуть FetchedPage. Кэш TTL 7 дней. Ошибки тихо пропускаем (логируем)."""
        if not urls:
            return []
        base = self._base_url()
        if not base:
            return []

        # 1. id страницы: прямой — из ссылки, короткая и «красивая» — через клиента
        url_to_pid: dict[str, Optional[str]] = {u: parse_page_id(u) for u in urls}
        unresolved = [u for u, pid in url_to_pid.items() if pid is None]

        results: list[FetchedPage] = []
        try:
            async with ConfluenceClient.from_db(self.db) as client:
                for u in unresolved:
                    try:
                        url_to_pid[u] = await client.resolve_page_id(u)
                    except Exception as e:
                        logger.warning("Confluence page id resolve %s failed: %s", u, e)

                # 2. Для каждого page_id — кэш или fetch
                for url, pid in url_to_pid.items():
                    if not pid:
                        continue
                    cached = self.db.execute(
                        select(ConfluencePageCache).where(ConfluencePageCache.page_id == pid)
                    ).scalar_one_or_none()
                    fresh = (
                        cached is not None
                        and cached.fetched_at >= datetime.utcnow() - CACHE_TTL
                        and cached.body_text is not None
                    )
                    if fresh:
                        results.append(FetchedPage(
                            page_id=pid, source_url=cached.source_url,
                            title=cached.title or "", body_text=cached.body_text or "",
                        ))
                        continue

                    try:
                        page = await client.get_page(pid)
                        text = html_to_text(page.body_html)[:MAX_BODY_CHARS]
                        if cached:
                            cached.source_url = url
                            cached.title = page.title
                            cached.body_text = text
                            cached.error = None
                            cached.fetched_at = datetime.utcnow()
                        else:
                            cached = ConfluencePageCache(
                                page_id=pid, source_url=url,
                                title=page.title, body_text=text,
                                error=None, fetched_at=datetime.utcnow(),
                            )
                            self.db.add(cached)
                        self.db.commit()
                        results.append(FetchedPage(
                            page_id=pid, source_url=url,
                            title=page.title, body_text=text,
                        ))
                    except (ConfluenceClientError, httpx.HTTPError) as e:
                        logger.warning("Confluence fetch %s failed: %s", pid, e)
                        if cached:
                            cached.error = str(e)[:512]
                            cached.fetched_at = datetime.utcnow()
                            self.db.commit()
        except ConfluenceClientError as e:
            logger.warning("Confluence client unavailable: %s", e)
            return []

        return results
