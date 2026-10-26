"""Jira Data Center HTTP client (REST API v2): вход по токену, повторы, пагинация."""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Callable, List, Optional, Tuple

import httpx

from app.config import get_settings
from app.connectors.changelog import status_changes
from app.connectors.jql import custom_field_number, jql_field_ref
from app.connectors.schemas import (
    JiraCommentSchema,
    JiraCommentsResponseSchema,
    JiraIssueSchema,
    JiraProjectSchema,
    JiraSearchResponseSchema,
    JiraUserSchema,
    JiraWorklogSchema,
    JiraWorklogsResponseSchema,
)

# Московское время без перехода на летнее (с 2014 года) — фиксированные +03:00.
JIRA_WALL_CLOCK_TZ = timezone(timedelta(hours=3), "MSK")


def _since_ms(since: datetime) -> int:
    """Граница-дата в мс эпохи; без пояса считается московской, не зависит от пояса сервера."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=JIRA_WALL_CLOCK_TZ)
    return int(since.timestamp() * 1000)


logger = logging.getLogger(__name__)

API_PREFIX = "/rest/api/2"

#: Пауза на 429, если сервер не прислал ``Retry-After`` числом секунд.
DEFAULT_RETRY_AFTER = 60

#: Поля задачи по умолчанию, если вызывающий не передал свой список.
DEFAULT_ISSUE_FIELDS = [
    "summary", "description", "issuetype", "status",
    "priority", "project", "parent", "creator", "reporter",
    "assignee", "created", "updated", "duedate",
]

_ORDER_BY_RE = re.compile(r"\border\s+by\b", re.IGNORECASE)

#: Сколько id ворклогов уходит в один POST /worklog/list (предел Jira).
WORKLOG_LIST_BATCH = 1000

#: Предел страниц опций поля: сервер, который не листает, не зациклит обход.
OPTIONS_MAX_PAGES = 50

#: Ожидание ответа Jira. Страница поиска с историей изменений у Jira DC
#: собирается долго: при 30 с полная синхронизация после переезда падала на
#: загрузке задач с пустым текстом сетевой ошибки (17.10.2026).
REQUEST_TIMEOUT = httpx.Timeout(120.0, connect=15.0)

#: Сколько раз повторять запрос, не дождавшийся ответа: тот же тяжёлый запрос
#: обычно не успевает и второй раз — поиск задач вместо этого уменьшает страницу.
TIMEOUT_ATTEMPTS = 2

#: После скольких удачных страниц подряд уменьшенная страница поиска растёт обратно.
PAGE_GROW_AFTER = 5


def _with_stable_order(jql: str) -> str:
    """Добавить ``ORDER BY key ASC``, если сортировка в JQL не задана.

    Поиск DC листается смещением: без устойчивой сортировки задача, изменённая
    во время обхода, уезжает в конец выборки, соседи сдвигаются, и одна из них
    пропускается.
    """
    if _ORDER_BY_RE.search(jql):
        return jql
    return f"{jql} ORDER BY key ASC"


def _retry_after_seconds(response: httpx.Response) -> int:
    """Пауза из ``Retry-After``; дата вместо числа или мусор — пауза по умолчанию."""
    try:
        return int(response.headers.get("Retry-After", DEFAULT_RETRY_AFTER))
    except ValueError:
        return DEFAULT_RETRY_AFTER


def _error_text(response: httpx.Response, method: str, url: str) -> str:
    """Текст ошибки с пояснениями Jira (``errorMessages`` и ``errors``), если они есть."""
    text = f"HTTP {response.status_code} {method} {url}"
    try:
        body = response.json()
    except ValueError:
        return text
    if not isinstance(body, dict):
        return text
    messages = [str(m) for m in body.get("errorMessages") or []]
    errors = body.get("errors")
    if isinstance(errors, dict):
        messages.extend(f"{field}: {msg}" for field, msg in errors.items())
    return f"{text}: {'; '.join(messages)}" if messages else text


def _failure_text(exc: Exception, method: str, url: str) -> str:
    """Текст сетевого сбоя: вид сбоя и запрос — у тайм-аута httpx пустой текст."""
    detail = str(exc).strip()
    return f"Request failed: {type(exc).__name__} {method} {url}" + (f": {detail}" if detail else "")


def _log_search_warnings(data: dict, jql: str) -> None:
    """Предупреждения поиска (``warningMessages``) — в журнал, а не в тишину."""
    warnings = data.get("warningMessages") or []
    if warnings:
        logger.warning("Jira: предупреждения поиска %r: %s", jql, "; ".join(map(str, warnings)))


class JiraClientError(Exception):
    """Base exception for Jira client errors."""
    pass


class JiraAuthError(JiraClientError):
    """Authentication failed."""
    pass


class JiraNetworkError(JiraClientError):
    """Jira не ответила и после повторов: сбой связи, а не ошибка запроса."""
    pass


class JiraTimeoutError(JiraNetworkError):
    """Jira не успела ответить за ``REQUEST_TIMEOUT`` и после повтора."""
    pass


class JiraServerError(JiraClientError):
    """Jira отвечала ошибкой сервера (5xx) и после повторов: сбой Jira, а не ошибка запроса."""
    pass


class JiraRateLimitError(JiraClientError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


class JiraClient:
    """Async HTTP client for Jira Data Center REST API v2.

    - Вход: ``Authorization: Bearer <персональный токен>``
    - Поиск задач: ``GET /search`` со смещением ``startAt`` и ``total``
    - Повторы с экспоненциальной паузой, отдельная ветка для 429
    """

    @classmethod
    def from_db(cls, db) -> "JiraClient":
        """Создать клиент с адресом и токеном из app_settings (fallback на .env)."""
        from app.models.app_setting import AppSetting

        def _get(key: str) -> Optional[str]:
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            return row.value if row else None

        return cls(base_url=_get("jira_base_url"), api_token=_get("jira_api_token"))

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        request_delay: float = 0.1,  # 100ms base for retry backoff
        max_retries: int = 5,
    ):
        settings = get_settings()

        self.base_url = (base_url or settings.jira_base_url or "").rstrip("/")
        self.api_token = api_token or settings.jira_api_token
        self.request_delay = request_delay
        self.max_retries = max_retries

        if not (self.base_url and self.api_token):
            raise JiraClientError(
                "Missing Jira credentials. Set JIRA_BASE_URL, JIRA_API_TOKEN"
            )

        self._headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        self._client: Optional[httpx.AsyncClient] = None
        #: Вызывается перед каждым запросом к Jira. Синк закрепляет здесь
        #: записанное, чтобы ожидание сети не держало строки заблокированными.
        self.before_request: Optional[Callable[[], None]] = None

    async def __aenter__(self) -> "JiraClient":
        """Context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers,
            timeout=REQUEST_TIMEOUT,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ):
        """HTTP-запрос с повторами.

        Повторяются только сетевые сбои, 5xx и 429 (пауза — ``Retry-After``).
        401/403 — ``JiraAuthError``, прочие 4xx — ``JiraClientError`` сразу,
        с пояснениями Jira: повтор ошибочного запроса ответа не изменит.
        5xx и после повторов — ``JiraServerError``.
        """
        if not self._client:
            raise JiraClientError("Client not initialized. Use async context manager.")

        if self.before_request is not None:
            self.before_request()
        url = f"{API_PREFIX}{path}"
        last = self.max_retries - 1

        for attempt in range(self.max_retries):
            # Пауза только на повторе; на 429 отдельная ветка ниже
            # спит столько, сколько попросил сервер (Retry-After).
            if attempt > 0:
                await asyncio.sleep(self.request_delay * (2 ** attempt))

            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                )
            except httpx.TimeoutException as e:
                # Не дождались ответа: повторяем один раз, дальше — отдельная ошибка,
                # по ней поиск задач уменьшает страницу.
                if attempt >= min(last, TIMEOUT_ATTEMPTS - 1):
                    raise JiraTimeoutError(_failure_text(e, method, url)) from e
                await asyncio.sleep(1.0 * (2 ** attempt))
                continue
            except httpx.RequestError as e:
                # Network errors (DNS fail / connection refused):
                # эти проблемы держатся секунды-минуты, экспоненциальный backoff
                # с базой 1s даёт 1, 2, 4, 8 сек — хватает на большинство глитчей.
                if attempt == last:
                    raise JiraNetworkError(_failure_text(e, method, url)) from e
                await asyncio.sleep(1.0 * (2 ** attempt))
                continue

            status = response.status_code
            if response.is_success:
                return response.json()

            if status == 429:
                retry_after = _retry_after_seconds(response)
                if attempt < last:
                    await asyncio.sleep(retry_after)
                    continue
                raise JiraRateLimitError(retry_after)

            if status == 401:
                raise JiraAuthError("Invalid credentials")
            if status == 403:
                raise JiraAuthError("Access forbidden. Check permissions.")
            if 400 <= status < 500:
                raise JiraClientError(_error_text(response, method, url))
            if attempt == last:
                error = JiraServerError if status >= 500 else JiraClientError
                raise error(_error_text(response, method, url))

        raise JiraClientError("Max retries exceeded")

    # === User methods ===

    async def get_myself(self) -> JiraUserSchema:
        """Get current authenticated user."""
        data = await self._request("GET", "/myself")
        return JiraUserSchema(**data)

    async def search_users(
        self,
        query: str,
        max_results: int = 20,
        include_inactive: bool = False,
    ) -> List[JiraUserSchema]:
        """Поиск пользователей Jira DC по логину, имени или почте.

        ``GET /user/search?username=`` — в DC параметр называется ``username``
        и ищет по всем трём признакам (начала слов); неактивные учётки
        возвращаются только с ``include_inactive``.
        """
        params: dict = {"username": query, "maxResults": max_results}
        if include_inactive:
            params["includeInactive"] = "true"
        raw = await self._request("GET", "/user/search", params=params)
        return [JiraUserSchema.model_validate(item) for item in raw]

    # === Project methods ===

    async def get_projects(self) -> List[JiraProjectSchema]:
        """Все проекты, видимые токену: ``GET /project`` отдаёт массив целиком."""
        data = await self._request("GET", "/project")
        return [JiraProjectSchema.model_validate(p) for p in data]

    async def iter_projects(self) -> AsyncIterator[JiraProjectSchema]:
        """Iterate through all projects."""
        for project in await self.get_projects():
            yield project

    # === Issue methods ===

    async def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 100,
        fields: Optional[List[str]] = None,
        expand: Optional[str] = None,
        lenient: bool = False,
    ) -> JiraSearchResponseSchema:
        """Одна страница поиска ``GET /search`` (смещение ``startAt``).

        По умолчанию ошибка в JQL — ``JiraClientError`` с пояснением Jira.
        ``lenient=True`` (``validateQuery=warn``) — только для поиска по списку
        ключей из базы: ключ задачи, которой больше нет в Jira, даёт
        предупреждение в журнал, а не ошибку всего запроса.
        """
        params: dict = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": ",".join(fields or DEFAULT_ISSUE_FIELDS),
        }
        if lenient:
            params["validateQuery"] = "warn"
        if expand:
            params["expand"] = expand
        data = await self._request("GET", "/search", params=params)
        _log_search_warnings(data, jql)
        return JiraSearchResponseSchema(**data)

    async def iter_issues(
        self,
        jql: str,
        max_results: int = 100,
        fields: Optional[List[str]] = None,
        expand: Optional[str] = None,
        lenient: bool = False,
    ) -> AsyncIterator[JiraIssueSchema]:
        """Все задачи по JQL до ``total``.

        Смещение растёт на число полученных задач: сервер может урезать
        ``max_results``. ``lenient`` — как в ``search_issues``.

        Страница не дождалась ответа (задачи с длинной историей) — она
        перечитывается вдвое меньшей, до одной задачи; после
        ``PAGE_GROW_AFTER`` удачных страниц подряд размер растёт обратно.
        """
        jql = _with_stable_order(jql)
        start_at = 0
        page_size = max_results
        ok_in_a_row = 0
        while True:
            try:
                response = await self.search_issues(
                    jql=jql,
                    start_at=start_at,
                    max_results=page_size,
                    fields=fields,
                    expand=expand,
                    lenient=lenient,
                )
            except JiraTimeoutError:
                if page_size == 1:
                    raise
                page_size = max(1, page_size // 2)
                ok_in_a_row = 0
                logger.warning(
                    "Jira не успела отдать страницу поиска (с %d): читаю по %d задач", start_at, page_size,
                )
                continue
            ok_in_a_row += 1
            if page_size < max_results and ok_in_a_row >= PAGE_GROW_AFTER:
                page_size = min(max_results, page_size * 2)
                ok_in_a_row = 0
            for issue in response.issues:
                yield issue
            start_at += len(response.issues)
            if not response.issues or start_at >= response.total:
                break

    async def iter_issue_keys(
        self,
        jql: str,
        page_size: int = 1000,
    ) -> AsyncIterator[Tuple[str, str]]:
        """Пары ``(ключ, id)`` всех задач по JQL — без разбора полей схемой.

        Для сверки задач при переезде: на десятки тысяч задач нужны только
        ключ и id.
        """
        jql = _with_stable_order(jql)
        start_at = 0
        while True:
            data = await self._request(
                "GET",
                "/search",
                params={
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": page_size,
                    "fields": "key",
                },
            )
            _log_search_warnings(data, jql)
            issues = data.get("issues") or []
            for issue in issues:
                yield issue["key"], str(issue["id"])
            start_at += len(issues)
            if not issues or start_at >= int(data.get("total") or 0):
                break

    async def get_statuses(self) -> list[dict]:
        """Справочник статусов: ``id``, ``name``, ``statusCategory.key``."""
        return await self._request("GET", "/status")

    async def get_issue_changelog(self, issue_key: str) -> dict:
        """Полная история изменений задачи: ``GET /issue/{key}?expand=changelog``."""
        data = await self._request(
            "GET",
            f"/issue/{issue_key}",
            params={"fields": "status", "expand": "changelog"},
        )
        return data.get("changelog") or {}

    async def get_status_changes(self, issue_key: str) -> List[Tuple[str, str]]:
        """История смен статуса задачи: ``(когда ISO-строкой, новый статус)``."""
        return status_changes(await self.get_issue_changelog(issue_key))

    # === Worklog methods ===

    async def get_worklogs_for_issue(
        self,
        issue_id: str,
        start_at: int = 0,
        max_results: int = 100,
    ) -> JiraWorklogsResponseSchema:
        """Get worklogs for a specific issue."""
        data = await self._request(
            "GET",
            f"/issue/{issue_id}/worklog",
            params={"startAt": start_at, "maxResults": max_results},
        )
        return JiraWorklogsResponseSchema(**data)

    async def iter_worklogs_for_issue(
        self,
        issue_id: str,
        max_results: int = 100,
    ) -> AsyncIterator[JiraWorklogSchema]:
        """Iterate through all worklogs for an issue."""
        start_at = 0
        while True:
            response = await self.get_worklogs_for_issue(
                issue_id=issue_id,
                start_at=start_at,
                max_results=max_results,
            )
            for worklog in response.worklogs:
                yield worklog
            if not response.has_more:
                break
            start_at += max_results

    # === Comment methods ===

    async def get_comments_for_issue(
        self,
        issue_id: str,
        start_at: int = 0,
        max_results: int = 100,
    ) -> JiraCommentsResponseSchema:
        """Get comments for a specific issue."""
        data = await self._request(
            "GET",
            f"/issue/{issue_id}/comment",
            params={"startAt": start_at, "maxResults": max_results},
        )
        return JiraCommentsResponseSchema(**data)

    async def iter_comments_for_issue(
        self,
        issue_id: str,
        max_results: int = 100,
    ) -> AsyncIterator[JiraCommentSchema]:
        """Iterate through all comments for an issue."""
        start_at = 0
        while True:
            response = await self.get_comments_for_issue(
                issue_id=issue_id,
                start_at=start_at,
                max_results=max_results,
            )
            for comment in response.comments:
                yield comment
            if not response.has_more:
                break
            start_at += max_results

    async def _iter_since_ids(self, path: str, since_ms: int) -> AsyncIterator[int]:
        """id ворклогов из ``/worklog/updated`` или ``/worklog/deleted`` с ``since_ms``.

        Страницы идут по ``lastPage``/``until``. Если на непоследней странице
        ``until`` нет или он не сдвинулся вперёд — ``JiraClientError``: обрыв
        списка не должен сойти за полный. id такой страницы отдаются до ошибки.
        """
        cursor = since_ms
        while True:
            data = await self._request("GET", path, params={"since": cursor})
            for item in data.get("values", []):
                yield item["worklogId"]
            if data.get("lastPage", True):
                return
            until = data.get("until")
            if not isinstance(until, int) or until <= cursor:
                raise JiraClientError(
                    f"Jira: {path} не сдвинул границу (since={cursor}, until={until}), список неполный"
                )
            cursor = until

    async def iter_deleted_worklog_ids(self, since: datetime) -> AsyncIterator[int]:
        """id ворклогов, удалённых с момента ``since``: ``GET /worklog/deleted``."""
        async for worklog_id in self._iter_since_ids(
            "/worklog/deleted", _since_ms(since)
        ):
            yield worklog_id

    async def iter_worklogs_updated_since(
        self,
        since_ms: int,
    ) -> AsyncIterator[JiraWorklogSchema]:
        """Все ворклоги, созданные или изменённые с ``since_ms`` (мс эпохи).

        ``GET /worklog/updated`` отдаёт только id; содержимое —
        ``POST /worklog/list`` пачками по ``WORKLOG_LIST_BATCH``. Пачка уходит,
        как только набралась, поэтому полный обход (``since_ms=0``) не держит
        в памяти весь список id.
        """
        batch: list[int] = []
        async for worklog_id in self._iter_since_ids("/worklog/updated", since_ms):
            batch.append(worklog_id)
            if len(batch) >= WORKLOG_LIST_BATCH:
                async for worklog in self._worklog_list(batch):
                    yield worklog
                batch = []
        if batch:
            async for worklog in self._worklog_list(batch):
                yield worklog

    async def _worklog_list(self, ids: list[int]) -> AsyncIterator[JiraWorklogSchema]:
        """Содержимое ворклогов по id: одна пачка ``POST /worklog/list``."""
        data = await self._request("POST", "/worklog/list", json={"ids": ids})
        for wl_data in data:
            yield JiraWorklogSchema(**wl_data)

    async def get_worklogs_updated_since(
        self,
        since: datetime,
    ) -> AsyncIterator[JiraWorklogSchema]:
        """То же, что :meth:`iter_worklogs_updated_since`, с границей-датой."""
        async for worklog in self.iter_worklogs_updated_since(_since_ms(since)):
            yield worklog

    # === Field discovery methods ===

    async def get_fields(self) -> list[dict]:
        """Получить список всех полей Jira (включая кастомные)."""
        data = await self._request("GET", "/field")
        return data

    async def get_editable_field_ids(self, issue_key: str) -> set[str]:
        """ID полей, доступных на карточке задачи.

        Jira хранит значения кастомных полей и после переезда задачи в проект,
        где такого поля на экране нет: значение остаётся в базе и приезжает по
        API, хотя никто его больше не видит и не может изменить. Единственный
        способ отличить живое значение от мёртвого — спросить, какие поля вообще
        доступны на карточке этой задачи.
        """
        data = await self._request("GET", f"/issue/{issue_key}/editmeta")
        fields = data.get("fields") or {}
        return set(fields.keys())

    async def get_issue_types(self) -> list[dict]:
        """Получить все типы задач Jira (каталог issuetype)."""
        data = await self._request("GET", "/issuetype")
        return data

    async def get_field_configured_options(self, field_id: str) -> list[str]:
        """Включённые опции select-поля: ``GET /customFields/{n}/options`` (Jira DC).

        Не кастомное поле, нет прав или нет опций (поле-пользователь) — пустой
        список; тогда вызывающий перебирает задачи. Страницы — ``page`` с 1;
        конец — ``isLast``, страница без новых опций (сервер не листает) или
        предел ``OPTIONS_MAX_PAGES`` (тогда тоже пусто: список неполный).
        """
        number = custom_field_number(field_id)
        if number is None:
            return []
        seen: set[str] = set()
        values: set[str] = set()
        for page_no in range(1, OPTIONS_MAX_PAGES + 1):
            try:
                page = await self._request(
                    "GET",
                    f"/customFields/{number}/options",
                    params={"page": page_no, "maxResults": 100, "useAllContexts": "true"},
                )
            except JiraClientError:
                # Неполный список выдал бы себя за полный — пусть лучше перебор задач.
                return []
            new = 0
            for opt in page.get("values") or []:
                opt_key = str(opt.get("id") or opt.get("value"))
                if opt_key in seen:
                    continue
                seen.add(opt_key)
                new += 1
                if not opt.get("disabled") and opt.get("value"):
                    values.add(opt["value"])
            if page.get("isLast") or not new:
                return sorted(values)
        logger.warning(
            "Jira: опции поля %s не кончились за %d страниц — перебор задач",
            field_id, OPTIONS_MAX_PAGES,
        )
        return []

    async def get_field_distinct_values(
        self,
        field_id: str,
        max_issues: int = 1000,
    ) -> list[str]:
        """Получить уникальные значения кастомного поля.

        Сначала пытаемся через сконфигурированные опции поля — это полный список
        и быстрее. Если опций нет (поле типа user/team picker), сканируем задачи.
        """
        options = await self.get_field_configured_options(field_id)
        if options:
            return options

        # Свежие задачи первыми: перебор ограничен max_issues, и старые задачи
        # дали бы давно не используемые значения. Задача, изменённая во время
        # обхода, может выпасть — для набора значений это не страшно.
        jql = f"{jql_field_ref(field_id)} is not EMPTY ORDER BY updated DESC"
        values: set[str] = set()
        start_at = 0
        # Мы просим только нужное кастомное поле, но Pydantic-схема ответа
        # требует базовые поля (summary/issuetype/status/project) — включаем их.
        required_fields = ["summary", "issuetype", "status", "project", field_id]
        while start_at < max_issues:
            response = await self.search_issues(
                jql=jql,
                start_at=start_at,
                max_results=100,
                fields=required_fields,
            )
            for issue in response.issues:
                raw = issue.fields._extra.get(field_id)
                if raw is None:
                    continue
                # Handle select/multi-select fields (dict with 'value' key)
                if isinstance(raw, dict) and "value" in raw:
                    values.add(raw["value"])
                elif isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict) and "value" in item:
                            values.add(item["value"])
                        elif isinstance(item, str):
                            values.add(item)
                elif isinstance(raw, str):
                    values.add(raw)
            start_at += len(response.issues)
            if not response.has_more:
                break
        return sorted(values)

    # === Utility methods ===

    async def test_connection(self) -> bool:
        """Test connection and credentials."""
        try:
            await self.get_myself()
            return True
        except JiraClientError:
            return False
