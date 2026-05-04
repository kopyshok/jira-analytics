"""Confluence Cloud REST client. Переиспользует Atlassian creds (тот же токен, что Jira)."""
import base64
import re
from dataclasses import dataclass
from typing import Optional

import httpx


class ConfluenceClientError(Exception):
    pass


@dataclass
class ConfluencePage:
    id: str
    title: str
    body_html: str


class ConfluenceClient:
    """Async Confluence Cloud client. Same Basic auth as Jira."""

    @classmethod
    def from_db(cls, db) -> "ConfluenceClient":
        from app.models.app_setting import AppSetting

        def _get(key: str) -> Optional[str]:
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            return row.value if row else None

        return cls(
            base_url=_get("jira_base_url") or "",
            email=_get("jira_email") or "",
            api_token=_get("jira_api_token") or "",
        )

    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        if not (base_url and email and api_token):
            raise ConfluenceClientError("Confluence credentials missing")
        self.base_url = base_url.rstrip("/")
        creds = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._headers = {"Authorization": f"Basic {creds}", "Accept": "application/json"}
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "ConfluenceClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers, timeout=30.0,
            follow_redirects=False,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def get_page(self, page_id: str) -> ConfluencePage:
        if not self._client:
            raise ConfluenceClientError("Use as async context manager")
        r = await self._client.get(
            f"/wiki/rest/api/content/{page_id}",
            params={"expand": "body.storage"},
        )
        if r.status_code != 200:
            raise ConfluenceClientError(
                f"GET page {page_id} → HTTP {r.status_code}: {r.text[:200]}"
            )
        data = r.json()
        return ConfluencePage(
            id=data["id"],
            title=data.get("title", ""),
            body_html=data.get("body", {}).get("storage", {}).get("value", ""),
        )

    async def resolve_tinyurl(self, url: str) -> Optional[str]:
        """Tinyurl `/wiki/x/{id}` → page_id через 302 redirect."""
        if not self._client:
            raise ConfluenceClientError("Use as async context manager")
        path = url.replace(self.base_url, "")
        if not path.startswith("/wiki/x/"):
            return None
        r = await self._client.get(path)
        if r.status_code != 302:
            return None
        loc = r.headers.get("Location", "")
        m = re.search(r"/pages/(\d+)", loc)
        return m.group(1) if m else None
