"""Проверка возможностей новой Jira: каждый запрос, нужный синку, вызван хотя бы раз.

Обязательные (без них отчёт не строится и применить нельзя): список
проектов, поиск задач, список полей, ворклоги (изменённые + содержимое).
Остальные сбои — предупреждения в отчёте.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.connectors.jql import jql_quote
from app.models import AppSetting

SEARCH_FIELDS = ["summary", "issuetype", "status", "project"]
WORKLOG_WINDOW = timedelta(days=30)
NO_SAMPLE = "Пропущено: нет задачи из проекта, который есть в новой Jira"


@dataclass
class ProbeResult:
    code: str
    title: str
    essential: bool
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _describe(exc: Exception) -> str:
    text = str(exc).strip()
    return text[:300] if text else exc.__class__.__name__


async def _check(
    results: list[ProbeResult],
    code: str,
    title: str,
    essential: bool,
    action: Callable[[], Awaitable[str]],
) -> None:
    try:
        detail = await action()
        results.append(ProbeResult(code, title, essential, True, detail or ""))
    except Exception as exc:  # noqa: BLE001 — любой сбой запроса попадает в отчёт
        results.append(ProbeResult(code, title, essential, False, _describe(exc)))


async def run_probe(
    db: Session,
    jira: Any,
    *,
    sample_project: Optional[str],
    sample_issue_key: Optional[str],
    team_field_id: Optional[str],
    now: datetime,
) -> list[ProbeResult]:
    """Вызвать каждый используемый синком запрос новой Jira; ошибки — в результат."""
    results: list[ProbeResult] = []
    login: dict[str, Optional[str]] = {"name": None}

    async def myself() -> str:
        user = await jira.get_myself()
        login["name"] = user.name
        return f"Вход выполнен: {user.display_name}"

    async def projects() -> str:
        return f"Проектов: {len(await jira.get_projects())}"

    async def search() -> str:
        jql = f"project = {jql_quote(sample_project)}" if sample_project else "order by created DESC"
        page = await jira.search_issues(jql, max_results=1, fields=SEARCH_FIELDS, expand="changelog")
        return f"Задач по запросу: {page.total}"

    async def fields() -> str:
        return f"Полей: {len(await jira.get_fields())}"

    async def statuses() -> str:
        return f"Статусов: {len(await jira.get_statuses())}"

    async def worklogs() -> str:
        since_ms = int((now - WORKLOG_WINDOW).replace(tzinfo=timezone.utc).timestamp() * 1000)
        stream = jira.iter_worklogs_updated_since(since_ms)
        try:
            async for _worklog in stream:
                return "Списания читаются"
        finally:
            await stream.aclose()
        return "За последние 30 дней списаний нет — содержимое не проверено"

    async def changelog() -> str:
        if not sample_issue_key:
            return NO_SAMPLE
        data = await jira.get_issue_changelog(sample_issue_key)
        return f"Записей истории: {len(data.get('histories') or [])}"

    async def editmeta() -> str:
        if not sample_issue_key:
            return NO_SAMPLE
        editable = await jira.get_editable_field_ids(sample_issue_key)
        if not editable:
            raise ValueError(
                "Список доступных на карточке полей пуст — у токена, видимо, нет прав "
                "на редактирование; сервис не будет очищать устаревшие значения полей"
            )
        return f"Полей на карточке: {len(editable)}"

    async def users() -> str:
        found = await jira.search_users(login["name"] or "a", max_results=5)
        return f"Найдено пользователей: {len(found)}"

    await _check(results, "myself", "Вход по токену", False, myself)
    await _check(results, "projects", "Список проектов", True, projects)
    await _check(results, "search", "Поиск задач", True, search)
    await _check(results, "fields", "Список полей", True, fields)
    await _check(results, "statuses", "Справочник статусов", False, statuses)
    await _check(results, "worklogs", "Списания: изменённые и их содержимое", True, worklogs)
    await _check(results, "changelog", "История изменений задачи", False, changelog)
    await _check(results, "editmeta", "Поля, доступные на карточке задачи", False, editmeta)

    # Клиент сам глотает ошибку запроса значений и отдаёт пустой список.
    team_title = "Значения поля команды"
    if not team_field_id:
        results.append(ProbeResult("team_options", team_title, False, False, "Поле команды не сопоставлено"))
    else:
        try:
            options = await jira.get_field_configured_options(team_field_id)
            if options:
                results.append(ProbeResult("team_options", team_title, False, True, f"Значений: {len(options)}"))
            else:
                results.append(ProbeResult(
                    "team_options", team_title, False, False,
                    "Список значений не получен — сервис возьмёт команды из задач",
                ))
        except Exception as exc:  # noqa: BLE001
            results.append(ProbeResult("team_options", team_title, False, False, _describe(exc)))

    await _check(results, "users", "Поиск пользователей", False, users)

    confluence_url = db.query(AppSetting.value).filter(AppSetting.key == "confluence_base_url").scalar()
    if confluence_url and confluence_url.strip():
        async def confluence() -> str:
            from app.connectors.confluence_client import ConfluenceClient

            async with ConfluenceClient.from_db(db) as client:
                user = await client.get_current_user()
            return f"Вход выполнен: {user.get('displayName') or user.get('username') or ''}".strip()

        await _check(results, "confluence", "Confluence", False, confluence)
    return results


def essential_failures(results: list[ProbeResult]) -> list[ProbeResult]:
    return [r for r in results if r.essential and not r.ok]
