"""Confluence Data Center REST client: свой адрес и персональный токен (Bearer)."""
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote_plus, urljoin, urlsplit

import httpx


class ConfluenceClientError(Exception):
    pass


@dataclass
class ConfluencePage:
    id: str
    title: str
    body_html: str


_PAGE_ID_RE = re.compile(r"(?:pageId=|/pages/)(\d+)")
_DISPLAY_RE = re.compile(r"/display/([^/?#]+)/([^?#]+)")


def page_id_from_url(url: str) -> Optional[str]:
    """id страницы из ``…/viewpage.action?pageId=N`` или ``…/pages/N/…``; иначе ``None``."""
    m = _PAGE_ID_RE.search(url)
    return m.group(1) if m else None


def base_url_pattern(base_url: str) -> str:
    """Регулярка адреса Confluence из настроек (без завершающего «/»).

    Схема — http или https, сервер — без учёта регистра; путь сервера
    (например ``/confluence``) — как есть.
    """
    parts = urlsplit(base_url.strip().rstrip("/"))
    return r"(?i:https?://" + re.escape(parts.netloc) + ")" + re.escape(parts.path)


def _json_object(r: httpx.Response) -> dict:
    """Тело ответа как объект JSON; страница входа или прокси вместо данных — ошибка."""
    try:
        data = r.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise ConfluenceClientError(
            "Confluence ответил не данными, а страницей — проверьте адрес и доступ"
        )
    return data


class ConfluenceClient:
    """Async Confluence Data Center client."""

    @classmethod
    def from_db(cls, db) -> "ConfluenceClient":
        """Адрес и токен — свои настройки Confluence (сервер отдельный от Jira)."""
        from app.models.app_setting import AppSetting

        def _get(key: str) -> Optional[str]:
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            return row.value if row else None

        return cls(
            base_url=_get("confluence_base_url") or "",
            api_token=_get("confluence_api_token") or "",
        )

    def __init__(self, base_url: str, api_token: str) -> None:
        if not (base_url and api_token):
            raise ConfluenceClientError("Не указаны адрес или токен Confluence")
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_token}", "Accept": "application/json"}
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

    def _http(self) -> httpx.AsyncClient:
        if not self._client:
            raise ConfluenceClientError("Use as async context manager")
        return self._client

    async def get_current_user(self) -> dict:
        """Пользователь токена — для проверки подключения."""
        r = await self._http().get("/rest/api/user/current")
        if r.status_code in (401, 403):
            raise ConfluenceClientError("Ошибка аутентификации: проверьте токен Confluence")
        if r.status_code != 200:
            raise ConfluenceClientError(f"Confluence ответил ошибкой (код {r.status_code})")
        return _json_object(r)

    async def get_page(self, page_id: str) -> ConfluencePage:
        r = await self._http().get(
            f"/rest/api/content/{page_id}",
            params={"expand": "body.storage"},
        )
        if r.status_code != 200:
            raise ConfluenceClientError(
                f"GET page {page_id} → HTTP {r.status_code}: {r.text[:200]}"
            )
        data = _json_object(r)
        try:
            return ConfluencePage(
                id=str(data["id"]),
                title=data.get("title") or "",
                body_html=(data.get("body") or {}).get("storage", {}).get("value") or "",
            )
        except (KeyError, AttributeError) as e:
            raise ConfluenceClientError(f"GET page {page_id}: неполный ответ ({e!r})") from e

    async def find_page_id(self, space_key: str, title: str) -> Optional[str]:
        """id страницы по ключу пространства и точному названию."""
        r = await self._http().get(
            "/rest/api/content",
            params={"spaceKey": space_key, "title": title, "limit": 1},
        )
        if r.status_code != 200:
            return None
        results = _json_object(r).get("results") or []
        try:
            return str(results[0]["id"]) if results else None
        except (KeyError, TypeError) as e:
            raise ConfluenceClientError(f"Поиск страницы: неполный ответ ({e!r})") from e

    async def resolve_page_id(self, url: str) -> Optional[str]:
        """id страницы по любой ссылке Confluence DC.

        Прямой id (``pageId=`` / ``/pages/N``) — сразу; короткая ``/x/…`` —
        по переадресации; ``/display/<пространство>/<название>`` — поиском по
        названию.
        """
        page_id = page_id_from_url(url)
        if page_id:
            return page_id
        path = self._relative_path(url)
        if path is None:
            return None
        if path.startswith("/x/"):
            r = await self._http().get(path)
            if not r.has_redirect_location:
                return None
            # Переадресация на чужой сервер — туда не ходим и токен не шлём.
            path = self._relative_path(urljoin(self.base_url + "/", r.headers["Location"]))
            if path is None:
                return None
            page_id = page_id_from_url(path)
            if page_id:
                return page_id
        return await self._display_page_id(path)

    def _relative_path(self, url: str) -> Optional[str]:
        """Путь ссылки после адреса из настроек (с «/» в начале); чужой адрес — ``None``."""
        m = re.match(base_url_pattern(self.base_url) + r"(/\S*)", url)
        return m.group(1) if m else None

    async def _display_page_id(self, path: str) -> Optional[str]:
        m = _DISPLAY_RE.search(path)
        if not m:
            return None
        return await self.find_page_id(unquote_plus(m.group(1)), unquote_plus(m.group(2)))
