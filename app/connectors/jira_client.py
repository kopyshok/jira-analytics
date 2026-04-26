"""Jira Cloud HTTP client with rate limiting and pagination."""

import asyncio
import base64
from datetime import datetime
from typing import Optional, List, AsyncIterator

import httpx

from app.config import get_settings
from app.connectors.schemas import (
    JiraUserSchema,
    JiraProjectSchema,
    JiraIssueSchema,
    JiraWorklogSchema,
    JiraCommentSchema,
    JiraSearchResponseSchema,
    JiraWorklogsResponseSchema,
    JiraProjectsResponseSchema,
    JiraCommentsResponseSchema,
)


class JiraClientError(Exception):
    """Base exception for Jira client errors."""
    pass


class JiraAuthError(JiraClientError):
    """Authentication failed."""
    pass


class JiraRateLimitError(JiraClientError):
    """Rate limit exceeded."""
    
    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


class JiraClient:
    """Async HTTP client for Jira Cloud REST API v3.

    Features:
    - Basic authentication with email + API token
    - Automatic pagination
    - Rate limiting with exponential backoff
    - Incremental sync support via JQL updated >= filter
    """

    @classmethod
    def from_db(cls, db) -> "JiraClient":
        """Создать клиент с credentials из app_settings (fallback на .env)."""
        from app.models.app_setting import AppSetting

        def _get(key: str) -> Optional[str]:
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            return row.value if row else None

        return cls(
            base_url=_get("jira_base_url"),
            email=_get("jira_email"),
            api_token=_get("jira_api_token"),
        )

    def __init__(
        self,
        base_url: Optional[str] = None,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        request_delay: float = 0.1,  # 100ms between requests
        max_retries: int = 3,
    ):
        settings = get_settings()

        self.base_url = (base_url or settings.jira_base_url or "").rstrip("/")
        self.email = email or settings.jira_email
        self.api_token = api_token or settings.jira_api_token
        self.request_delay = request_delay
        self.max_retries = max_retries
        
        if not all([self.base_url, self.email, self.api_token]):
            raise JiraClientError(
                "Missing Jira credentials. Set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN"
            )
        
        # Build auth header
        credentials = f"{self.email}:{self.api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        
        self._headers = {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self) -> "JiraClient":
        """Context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers,
            timeout=30.0,
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
    ) -> dict:
        """Make HTTP request with retry logic."""
        if not self._client:
            raise JiraClientError("Client not initialized. Use async context manager.")
        
        url = f"/rest/api/3{path}"
        
        for attempt in range(self.max_retries):
            try:
                # Rate limiting delay
                if attempt > 0 or self.request_delay > 0:
                    delay = self.request_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                )
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    raise JiraRateLimitError(retry_after)
                
                # Handle auth errors
                if response.status_code == 401:
                    raise JiraAuthError("Invalid credentials")
                
                if response.status_code == 403:
                    raise JiraAuthError("Access forbidden. Check permissions.")
                
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                if attempt == self.max_retries - 1:
                    raise JiraClientError(f"HTTP error: {e}")
            except httpx.RequestError as e:
                if attempt == self.max_retries - 1:
                    raise JiraClientError(f"Request failed: {e}")
        
        raise JiraClientError("Max retries exceeded")
    
    # === User methods ===
    
    async def get_myself(self) -> JiraUserSchema:
        """Get current authenticated user."""
        data = await self._request("GET", "/myself")
        return JiraUserSchema(**data)
    
    async def get_users(
        self,
        start_at: int = 0,
        max_results: int = 50,
    ) -> List[JiraUserSchema]:
        """Get users from Jira (requires admin permissions)."""
        data = await self._request(
            "GET",
            "/users/search",
            params={"startAt": start_at, "maxResults": max_results},
        )
        return [JiraUserSchema(**user) for user in data]
    
    async def search_users(
        self,
        query: str,
        max_results: int = 20,
    ) -> List[JiraUserSchema]:
        """Поиск пользователей Jira по имени/e-mail.

        Использует ``/rest/api/3/user/search`` (не путать с
        ``/rest/api/3/users/search``, который возвращает всех пользователей,
        включая ботов и inactive). Для UI-автокомплита нужен query-based.
        """
        raw = await self._request(
            "GET",
            "/user/search",
            params={"query": query, "maxResults": max_results},
        )
        return [JiraUserSchema.model_validate(item) for item in raw]

    async def iter_users(self, max_results: int = 50) -> AsyncIterator[JiraUserSchema]:
        """Iterate through all users with pagination."""
        start_at = 0
        while True:
            users = await self.get_users(start_at=start_at, max_results=max_results)
            if not users:
                break
            for user in users:
                yield user
            if len(users) < max_results:
                break
            start_at += max_results
    
    # === Project methods ===
    
    async def get_projects(
        self,
        start_at: int = 0,
        max_results: int = 50,
    ) -> JiraProjectsResponseSchema:
        """Get projects with pagination."""
        data = await self._request(
            "GET",
            "/project/search",
            params={"startAt": start_at, "maxResults": max_results},
        )
        return JiraProjectsResponseSchema(**data)
    
    async def iter_projects(
        self,
        max_results: int = 50,
    ) -> AsyncIterator[JiraProjectSchema]:
        """Iterate through all projects."""
        start_at = 0
        while True:
            response = await self.get_projects(
                start_at=start_at,
                max_results=max_results,
            )
            for project in response.values:
                yield project
            if not response.has_more:
                break
            start_at += max_results
    
    # === Issue methods ===
    
    async def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 100,
        fields: Optional[List[str]] = None,
        next_page_token: Optional[str] = None,
    ) -> JiraSearchResponseSchema:
        """Search issues using JQL (GET /search/jql — cursor-based; startAt ignored).

        Pass ``next_page_token`` from the previous response to fetch the next page.
        """
        default_fields = [
            "summary", "description", "issuetype", "status",
            "priority", "project", "parent", "creator",
            "assignee", "created", "updated",
            "statuscategorychangedate", "duedate",
        ]

        params: dict = {
            "jql": jql,
            "maxResults": max_results,
            "fields": ",".join(fields or default_fields),
        }
        if next_page_token:
            params["nextPageToken"] = next_page_token
        else:
            params["startAt"] = start_at

        data = await self._request("GET", "/search/jql", params=params)
        return JiraSearchResponseSchema(**data)

    async def iter_issues(
        self,
        jql: str,
        max_results: int = 100,
        fields: Optional[List[str]] = None,
    ) -> AsyncIterator[JiraIssueSchema]:
        """Iterate through issues matching JQL (cursor-based pagination)."""
        next_page_token: Optional[str] = None
        while True:
            response = await self.search_issues(
                jql=jql,
                max_results=max_results,
                fields=fields,
                next_page_token=next_page_token,
            )
            for issue in response.issues:
                yield issue
            if not response.has_more:
                break
            next_page_token = response.nextPageToken
            if not next_page_token:
                break
    
    async def get_issues_updated_since(
        self,
        project_keys: List[str],
        since: Optional[datetime] = None,
        max_results: int = 100,
        extra_fields: Optional[List[str]] = None,
    ) -> AsyncIterator[JiraIssueSchema]:
        """Get issues updated since a given timestamp (incremental sync).

        ``extra_fields`` — дополнительные кастомные поля (например, ID полей команды),
        добавляются к стандартному списку и попадают в ``JiraIssueFieldsSchema._extra``.
        """
        projects_jql = ", ".join(f'"{k}"' for k in project_keys)
        jql = f"project in ({projects_jql})"

        if since:
            # Format: "2024-01-15 10:30"
            since_str = since.strftime("%Y-%m-%d %H:%M")
            jql += f' AND updated >= "{since_str}"'

        jql += " ORDER BY updated ASC"

        fields = None
        if extra_fields:
            default_fields = [
                "summary", "description", "issuetype", "status",
                "priority", "project", "parent", "creator",
                "assignee", "created", "updated",
                "statuscategorychangedate", "duedate",
            ]
            fields = default_fields + list(extra_fields)

        async for issue in self.iter_issues(jql=jql, max_results=max_results, fields=fields):
            yield issue
    
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

    async def get_worklogs_updated_since(
        self,
        since: datetime,
    ) -> AsyncIterator[JiraWorklogSchema]:
        """Get all worklogs updated since timestamp using bulk API.
        
        Note: This uses the /worklog/updated endpoint which returns
        worklog IDs, then fetches each worklog individually.
        For MVP, we fetch worklogs per issue instead.
        """
        # For MVP: This requires fetching issue by issue
        # In future, implement /worklog/updated bulk endpoint
        raise NotImplementedError(
            "Use iter_worklogs_for_issue per issue. "
            "Bulk worklog API will be added in future version."
        )
    
    # === Field discovery methods ===

    async def get_fields(self) -> list[dict]:
        """Получить список всех полей Jira (включая кастомные)."""
        data = await self._request("GET", "/field")
        return data

    async def get_issue_types(self) -> list[dict]:
        """Получить все типы задач Jira (каталог issuetype)."""
        data = await self._request("GET", "/issuetype")
        return data

    async def get_field_configured_options(self, field_id: str) -> list[str]:
        """Получить все сконфигурированные опции select/multi-select поля.

        Обходит все контексты поля и возвращает объединение включённых опций.
        Возвращает пустой список, если поле не имеет опций (user/team picker и т.п.).
        """
        values: set[str] = set()
        try:
            contexts = await self._request("GET", f"/field/{field_id}/context")
        except JiraClientError:
            return []
        for ctx in contexts.get("values", []):
            ctx_id = ctx.get("id")
            if not ctx_id:
                continue
            start_at = 0
            while True:
                page = await self._request(
                    "GET",
                    f"/field/{field_id}/context/{ctx_id}/option",
                    params={"startAt": start_at, "maxResults": 100},
                )
                for opt in page.get("values", []):
                    if opt.get("disabled"):
                        continue
                    val = opt.get("value")
                    if val:
                        values.add(val)
                if page.get("isLast", True):
                    break
                start_at += 100
        return sorted(values)

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

        jql = f'"{field_id}" is not EMPTY ORDER BY updated DESC'
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
            if not response.has_more:
                break
            start_at += 100
        return sorted(values)

    # === Utility methods ===
    
    async def test_connection(self) -> bool:
        """Test connection and credentials."""
        try:
            await self.get_myself()
            return True
        except JiraClientError:
            return False
