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
    JiraSearchResponseSchema,
    JiraWorklogsResponseSchema,
    JiraProjectsResponseSchema,
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
    ) -> JiraSearchResponseSchema:
        """Search issues using JQL."""
        default_fields = [
            "summary", "description", "issuetype", "status",
            "priority", "project", "parent", "creator",
            "assignee", "created", "updated",
        ]
        
        data = await self._request(
            "GET",
            "/search",
            params={
                "jql": jql,
                "startAt": start_at,
                "maxResults": max_results,
                "fields": ",".join(fields or default_fields),
            },
        )
        return JiraSearchResponseSchema(**data)
    
    async def iter_issues(
        self,
        jql: str,
        max_results: int = 100,
        fields: Optional[List[str]] = None,
    ) -> AsyncIterator[JiraIssueSchema]:
        """Iterate through issues matching JQL."""
        start_at = 0
        while True:
            response = await self.search_issues(
                jql=jql,
                start_at=start_at,
                max_results=max_results,
                fields=fields,
            )
            for issue in response.issues:
                yield issue
            if not response.has_more:
                break
            start_at += max_results
    
    async def get_issues_updated_since(
        self,
        project_keys: List[str],
        since: Optional[datetime] = None,
        max_results: int = 100,
    ) -> AsyncIterator[JiraIssueSchema]:
        """Get issues updated since a given timestamp (incremental sync)."""
        projects_jql = ", ".join(f'"{k}"' for k in project_keys)
        jql = f"project in ({projects_jql})"
        
        if since:
            # Format: "2024-01-15 10:30"
            since_str = since.strftime("%Y-%m-%d %H:%M")
            jql += f' AND updated >= "{since_str}"'
        
        jql += " ORDER BY updated ASC"
        
        async for issue in self.iter_issues(jql=jql, max_results=max_results):
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
    
    # === Utility methods ===
    
    async def test_connection(self) -> bool:
        """Test connection and credentials."""
        try:
            await self.get_myself()
            return True
        except JiraClientError:
            return False
