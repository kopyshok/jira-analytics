"""Jira DC в памяти для тестов переезда: те же методы, что у JiraClient (план 1)."""
from __future__ import annotations

import re
from typing import Any, AsyncIterator, Iterable, Optional

from app.connectors.jira_client import JiraClientError
from app.connectors.schemas import (
    JiraProjectSchema,
    JiraSearchResponseSchema,
    JiraUserSchema,
    JiraWorklogSchema,
)


def dc_user(key: str, name: str, display_name: str, active: bool = True) -> JiraUserSchema:
    """Пользователь DC: ``key`` — идентичность, ``name`` — логин."""
    return JiraUserSchema.model_validate(
        {"key": key, "name": name, "displayName": display_name, "active": active}
    )


def dc_worklog(
    worklog_id: str,
    issue_id: str,
    author: JiraUserSchema,
    started_utc: str,
    seconds: int,
) -> JiraWorklogSchema:
    """Ворклог DC; ``started_utc`` — как шлёт DC, например ``2026-09-10T07:00:00.000+0000``."""
    return JiraWorklogSchema.model_validate({
        "id": worklog_id,
        "issueId": issue_id,
        "author": {
            "key": author.jira_account_id,
            "name": author.name,
            "displayName": author.display_name,
            "active": author.is_active,
        },
        "started": started_utc,
        "timeSpentSeconds": seconds,
    })


def _user_search_matches(query: str, user: JiraUserSchema) -> bool:
    """Как ``/user/search`` DC: начало логина, почты, ФИО или любого слова ФИО.

    Без учёта регистра; «ё» и «е» — разные буквы.
    """
    wanted = query.strip().lower()
    if not wanted:
        return False
    display = user.display_name.lower()
    texts = [(user.name or "").lower(), (user.email or "").lower(), display, *display.split()]
    return any(text.startswith(wanted) for text in texts)


class FakeJira:
    """``fail`` — имена методов, которые поднимают ошибку (сбой запроса к Jira)."""

    def __init__(
        self,
        *,
        projects: Optional[dict[str, str]] = None,
        issues: Optional[dict[str, list[tuple[str, str]]]] = None,
        worklogs: Optional[list[JiraWorklogSchema]] = None,
        users: Optional[list[JiraUserSchema]] = None,
        fields: Optional[list[dict]] = None,
        fail: Iterable[str] = (),
        field_options: Optional[list[str]] = None,
        statuses: Optional[list[dict]] = None,
        editable_fields: Optional[set[str]] = None,
    ) -> None:
        self.projects = projects or {}
        self.issues = issues or {}
        self.worklogs = worklogs or []
        self.users = users or []
        self.fields = fields if fields is not None else []
        self.fail = set(fail)
        self.field_options = field_options if field_options is not None else ["Команда А"]
        self.statuses = statuses if statuses is not None else [
            {"id": "1", "name": "Открыта", "statusCategory": {"key": "new"}},
        ]
        self.editable_fields = editable_fields if editable_fields is not None else {"summary", "customfield_11092"}
        self.calls: list[tuple[str, Any]] = []

    async def __aenter__(self) -> "FakeJira":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    def _call(self, name: str, arg: Any = None) -> None:
        self.calls.append((name, arg))
        if name in self.fail:
            raise JiraClientError(f"{name}: сервер недоступен")

    async def get_myself(self) -> JiraUserSchema:
        self._call("get_myself")
        return dc_user("JIRAUSER1", "admin_login", "Администратор")

    async def get_projects(self) -> list[JiraProjectSchema]:
        self._call("get_projects")
        return [JiraProjectSchema(id=pid, key=key, name=key) for key, pid in self.projects.items()]

    async def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 100,
        fields: Optional[list[str]] = None,
        expand: Optional[str] = None,
        lenient: bool = False,
    ) -> JiraSearchResponseSchema:
        self._call("search_issues", jql)
        project = re.match(r'project = "([^"]+)"', jql)
        if project and project.group(1) not in self.projects:
            # Как DC: поиск по несуществующему проекту — ошибка запроса, а не пустая выдача.
            raise JiraClientError(
                f"HTTP 400 GET /rest/api/2/search: The value '{project.group(1)}' does not exist "
                "for the field 'project'."
            )
        return JiraSearchResponseSchema.model_validate(
            {"startAt": start_at, "maxResults": max_results, "total": 0, "issues": []}
        )

    async def iter_issue_keys(self, jql: str, page_size: int = 1000) -> AsyncIterator[tuple[str, str]]:
        self._call("iter_issue_keys", jql)
        project = jql.split('"')[1]
        for pair in self.issues.get(project, []):
            yield pair

    async def iter_worklogs_updated_since(self, since_ms: int) -> AsyncIterator[JiraWorklogSchema]:
        self._call("iter_worklogs_updated_since", since_ms)
        for worklog in self.worklogs:
            yield worklog

    async def get_fields(self) -> list[dict]:
        self._call("get_fields")
        return list(self.fields)

    async def get_statuses(self) -> list[dict]:
        self._call("get_statuses")
        return list(self.statuses)

    async def get_issue_changelog(self, issue_key: str) -> dict:
        self._call("get_issue_changelog", issue_key)
        return {"total": 0, "histories": []}

    async def get_editable_field_ids(self, issue_key: str) -> set[str]:
        self._call("get_editable_field_ids", issue_key)
        return set(self.editable_fields)

    async def get_field_configured_options(self, field_id: str) -> list[str]:
        self._call("get_field_configured_options", field_id)
        return list(self.field_options)

    async def search_users(
        self, query: str, max_results: int = 20, include_inactive: bool = False,
    ) -> list[JiraUserSchema]:
        self._call("search_users", query)
        found = [
            u for u in self.users
            if (u.is_active or include_inactive) and _user_search_matches(query, u)
        ]
        return found[:max_results]
