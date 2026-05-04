"""ConfluenceService — extract Confluence-ссылок, fetch с кэшем, html→text."""
import re
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.confluence_client import ConfluenceClient, ConfluenceClientError
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


_URL_RE = re.compile(
    r"https?://[\w\.\-]+\.atlassian\.net/wiki/(?:spaces/[^\s/]+/pages/\d+[^\s)]*|x/[A-Za-z0-9]+)"
)


def extract_confluence_urls(text: Optional[str], base_url: str) -> list[str]:
    """Достать уникальные Confluence-ссылки на тот же tenant."""
    if not text or not base_url:
        return []
    host = urlparse(base_url).netloc
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,);")
        if urlparse(url).netloc != host:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def parse_page_id(url: str) -> Optional[str]:
    """`/wiki/spaces/.../pages/{id}/...` → id. Tinyurl возвращает None — резолв через client."""
    m = re.search(r"/pages/(\d+)", url)
    return m.group(1) if m else None


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
        row = self.db.query(AppSetting).filter(AppSetting.key == "jira_base_url").first()
        return row.value if row and row.value else None

    async def fetch_pages(self, urls: list[str]) -> list[FetchedPage]:
        """Для каждого URL вернуть FetchedPage. Кэш TTL 7 дней. Ошибки тихо пропускаем (логируем)."""
        if not urls:
            return []
        base = self._base_url()
        if not base:
            return []

        # 1. Резолвим page_id (tinyurl → fetch redirect, прочее regex)
        url_to_pid: dict[str, Optional[str]] = {u: parse_page_id(u) for u in urls}
        unresolved = [u for u, pid in url_to_pid.items() if pid is None]

        client_cm = ConfluenceClient.from_db(self.db)
        results: list[FetchedPage] = []
        try:
            async with client_cm as client:
                for u in unresolved:
                    try:
                        url_to_pid[u] = await client.resolve_tinyurl(u)
                    except Exception as e:
                        logger.warning("tinyurl resolve %s failed: %s", u, e)

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
                    except ConfluenceClientError as e:
                        logger.warning("Confluence fetch %s failed: %s", pid, e)
                        if cached:
                            cached.error = str(e)[:512]
                            cached.fetched_at = datetime.utcnow()
                            self.db.commit()
        except ConfluenceClientError as e:
            logger.warning("Confluence client unavailable: %s", e)
            return []

        return results
